# BamToCountMuts.py
import logging
from argparse import ArgumentParser
from collections import Counter, defaultdict
import pysam
from math import sqrt

def Wilson(positive,  total) :
    """Get Wilson confidence intervals for a position"""
    if total == 0:
        return 0

    z = 1.96 #1.96 = 95%
    phat = float(positive) / total
    positiveCI = (phat 
                  + z * z / (2 * total) 
                  + z * sqrt(
                      (phat * (1 - phat) + z * z / (4 * total)) / total
                      )
                  ) / ( 1 + z * z / total)
    negativeCI =  (phat 
                   + z * z / (2 * total) 
                   - z * sqrt(
                       (phat * (1 - phat) + z * z / (4 * total)) / total
                       )
                   ) / (1 + z * z / total)

    return  (phat, positiveCI , negativeCI )

class Bed_File:
    def __init__(self, inFile):
        self.file = open(inFile, 'r')
        
    def __iter__(self):
        return(self)
    
    def __next__(self):
        myLine = self.file.readline()
        if myLine != "":
            return(Bed_Line(*myLine.strip().split()))
        else:
            raise StopIteration
            
class Bed_Line:
    def __init__(self, 
                 chrom, 
                 startPos, 
                 endPos, 
                 name="",
                 score="", 
                 strand="+",
                 thickStart="", 
                 thickEnd="",
                 itemRGB="", 
                 blockCount="",
                 blockSizes="", 
                 blockStarts=""):
        self.chrom = chrom
        self.startPos = int(startPos)
        self.endPos = int(endPos)
        if name == "":
            self.name = f"{self.chrom}:{self.startPos}-{self.endPos}"
        else:
            self.name = name
        if score == '':
            self.score = 0
        else:
            self.score = int(score)
        if strand in (".","+","-"):
            self.strand = strand
        else:
            self.strand = "."
        if thickStart == "":
            self.thickStart = self.startPos
        else:
            self.thickStart = int(thickStart)
        if thickEnd == "":
            self.thickEnd = self.endPos
        else:
            self.thickEnd = int(thickEnd)
        if itemRGB == "":
            self.itemRBG = None
        else:
            self.itemRGB = itemRGB
        if blockCount == "":
            self.blockCount = 1
        else:
            self.blockCount = int(blockCount)
        if blockSizes == "":
            self.blockSizes = [abs(self.endPos - self.startPos)]
        else:
            self.blockSizes = [int(x) for x in blockSizes.split(',')]
        if blockStarts == "":
            self.blockStarts = [0]
        else:
            self.blockStarts = [int(x) for x in blockStarts.split(',')]
    
    def samtoolsStr(self):
        return(f"{self.chrom}:{self.startPos}:{self.endPos}")
    
    def get_subregions(self):
        if self.strand == '+':
            return([Bed_Line(
                self.chrom, 
                self.startPos + self.blockStarts[x], 
                self.startPos + self.blockStarts[x] + self.blockSizes[x], 
                f"{self.name}_block{x + 1}", 
                self.score, 
                self.strand
                ) for x in range(len(self.blockStarts))])
        elif self.strand == '-':
            return([Bed_Line(
                self.chrom, 
                self.startPos + self.blockStarts[-x - 1], 
                self.startPos + self.blockStarts[-x - 1] + self.blockSizes[-x - 1], 
                f"{self.name}_block{x + 1}", 
                self.score, 
                self.strand
                ) for x in range(len(self.blockStarts))])
        
    def contains(self, inChr, inPos):
        if (
                inChr == self.chrom
                and inPos >= self.startPos
                and inPos < self.endPos
                ):
            return(True)
        else:
            return(False)
    
def getParams():
    parser = ArgumentParser(
        description=(
            f"Make a mutpos vcf file from a post-procesing duplex "
            f"sequencing BAM file.  Note that this program will fail if"
            f" the maximum depth in your bam file is > 8000.  "
            )
        )
    parser.add_argument(
        '-i', '--inBam', 
        action ='store', 
        dest = 'inBam', 
        help = 'An imput bam file. If None, defaults to stdin. [%(default)s]', 
        default = None
        )
    parser.add_argument(
        '-b', '--inBed', 
        action ='store', 
        dest = 'inBed', 
        help = 'An input bed file. If None, processes all positions. [%(default)s]', 
        default = None
        )
    parser.add_argument(
        '-f', '--inFasta', 
        action ='store', 
        dest = 'in_fasta', 
        help = 'An input bed file. If None, processes all positions. [%(default)s]', 
        default = None
        )
    parser.add_argument(
        '-o', '--outfile', 
        action = 'store', 
        dest = 'out_file', 
        help = 'A filename for the output file.  If None, outputs to stdout.  [%(default)s]', 
        default = None
        )
    parser.add_argument(
        "--round", 
        action="store", 
        type=int, 
        dest="round", 
        help="How many digits to round frequencies to.", 
        default = 4
        )
    parser.add_argument(
        '--logLevel', 
        action="store", 
        dest="logLvl", 
        default="Info",
        help=(f"Identification for how much information gets output. "
              f"Acceptable levels are: 'DEBUG', 'INFO', 'WARNING', "
              f"'ERROR', and 'CRITICAL'.  "
              )
        )
    parser.add_argument(
        '--samp_name', 
        action='store', 
        dest='sampName',
        default=None,
        help='A name for the sample in the output VCF file.  '
        )
    parser.add_argument(
        "-d", "--depth", 
        action = "store", 
        type = int, 
        dest = "mindepth", 
        default = 20,
        help = "Minimum depth for counting mutations at a site [20]"
        )
    parser.add_argument(
        "-c", "--min_clonality", 
        action = "store", 
        type = float, 
        dest = "min_clonality", 
        default = 0,
        help = (f"Minimum (exclusive) cutoff of mutant reads for scoring a "
                f"clonal mutation [0]"
                )
        )
    parser.add_argument(
        "-C", "--max_clonality", 
        action = "store", 
        type = float, 
        dest = "max_clonality", 
        default = 0.1,
        help = (f"Maximum (inclusive) cutoff of mutant reads for scoring a "
                f"clonal mutation [%(default)s]"
                )
        )
    parser.add_argument(
        "-n", "--n_cutoff", 
        action = "store", 
        type = float, 
        dest = "n_cutoff", 
        default = 0.05,
        help = "Maximum fraction of N's allowed to score a position [0.05]"
        )
    parser.add_argument(
        '-u', '--unique', 
        action = 'store_true', 
        dest = 'unique', 
        help = 'Run countMutsUnique instead of countMuts'
        )
    parser.add_argument(
        "--outputType", 
        action="store", 
        dest="outType", 
        default="GB", 
        choices=["GB","G","B",
                 "BG", "N","GN",
                 "BN","GBN","BGN",
                 "NB","NG","NGB",
                 "NBG","BNG","GNB"
                 ],
        help=(
            f"Select which sections to output, in addition to 'OVERALL'.  "
            f"String of one or more of 'G' and 'B'.  "
            f"G -> output GENE sections for each bed line; "
            f"B -> output 'BLOCK' sections for each block in the bed "
            f"line (if present); 'N' -> Only output overall frequencies.  "
            f"Overrides all other options.  "
            )
        )
    parser.add_argument(
        "--sumType", 
        action="store", 
        dest="sumType", 
        default="GT", 
        choices=["GT","GB","BT","BB"],
        help=(
            f"Select how to sum for 'OVERALL' and 'GENE' sections, "
            f"where 'GENE' represents a single bed line. "
            f"The first character controls summing for overall: "
            f"G -> OVERALL = sum(GENEs); "
            f"B -> OVERALL = sum(BLOCKs).  "
            f"In sum(GENEs) mode, this will ignore BLOCKs for the "
            f"purposes of calculating OVERALL.  "
            f"The second character controls summing for each GENE: "
            f"T -> GENE = Whole gene, ignoring BLOCKs; "
            f"B -> GENE = sum(BLOCKs).  "
            )
        )
    return(parser.parse_args())

class countMutsEngine:
    def __init__(self, 
                 inBam, 
                 inFasta, 
                 inBed=None, 
                 unique=False, 
                 Nprop=1, 
                 minDepth=1, 
                 minC=0, 
                 maxC=1, 
                 sampName=None
                 ):
        self.params = {
           "inBam":inBam, 
           "inFasta":inFasta, 
           "inBed":inBed, 
           "unique": unique, 
           "Nprop": Nprop, 
           "minDepth": minDepth, 
           "minC": minC, 
           "maxC": maxC
           }
        self.inBam = pysam.AlignmentFile(inBam, "rb")
        if sampName is None:
            self.sample = "Sample"
        else:
            self.sample = sampName
        self.minC = minC
        self.maxC = maxC
        self.inFasta = pysam.FastaFile(inFasta)
        self.rmNumTable = {ord(c): None for c in '1234567890'}
        if inBed is None:
            self.myBed = None
        else:
            self.myBed = Bed_File(inBed)
        self.mutsCounts = {
            "Aseq": 0, 
            "A>T": 0,
            "A>C": 0,
            "A>G": 0,
            "Tseq": 0,
            "T>A": 0,
            "T>C": 0,
            "T>G": 0,
            "Cseq": 0,
            "C>A": 0,
            "C>T": 0,
            "C>G": 0,
            "Gseq": 0,
            "G>A": 0,
            "G>T": 0,
            "G>C": 0,
            "ins":defaultdict(int),
            "dels": defaultdict(int),
            "DP": 0
            }
        self.geneCounts = {}
        self.blockCounts = {}
    
    def processLines(self, 
                     roundLevel
                     ):
        linesProcessed = 0
        if self.myBed is None:
            for pileup_column in self.inBam.pileup(
                    fastafile=self.inFasta, 
                    truncate=True, 
                    stepper="nofilter", 
                    max_depth=1000000, 
                    min_base_quality = 0
                    ):
                
                lnCnts = self.CountLine(
                    pileup_column, 
                    roundLevel,
                    self.params["unique"],
                    self.params["Nprop"], 
                    self.params["minDepth"], 
                    self.params["minC"], 
                    self.params["maxC"]
                    )
                self.mutsCounts["DP"] += lnCnts["DP"]
                self.mutsCounts[f"{lnCnts['RefBase']}seq"] += lnCnts["DP"]
                for xIter in ("A","C","G","T"):
                    if xIter != lnCnts["RefBase"]:
                        self.mutsCounts[f"{lnCnts['RefBase']}>{xIter}"] += lnCnts[xIter]
                for xIter in lnCnts["ins"]:
                    self.mutsCounts["ins"][xIter] += lnCnts["ins"][xIter]
                for xIter in lnCnts["dels"]:
                    self.mutsCounts["dels"][xIter] += lnCnts["dels"][xIter]
                
            linesProcessed += 1
            if linesProcessed % 1000 == 0:
                logging.info(f"{linesProcessed} lines processed...")
        else:
            linesCounted = []
            for myRegion in self.myBed:
                regStr = myRegion.samtoolsStr()
                subregions = myRegion.get_subregions()
                self.geneCounts[regStr] = {
                    "name": myRegion.name, 
                    "str": regStr, 
                    "Aseq": 0, 
                    "A>T": 0,
                    "A>C": 0,
                    "A>G": 0,
                    "Tseq": 0,
                    "T>A": 0,
                    "T>C": 0,
                    "T>G": 0,
                    "Cseq": 0,
                    "C>A": 0,
                    "C>T": 0,
                    "C>G": 0,
                    "Gseq": 0,
                    "G>A": 0,
                    "G>T": 0,
                    "G>C": 0,
                    "ins":defaultdict(int),
                    "dels": defaultdict(int),
                    "DP": 0, 
                    "blocks":len(subregions)
                    }
                if not ( 
                        len(subregions) == 1
                        and subregions[0].startPos == myRegion.startPos
                        and subregions[0].endPos == myRegion.endPos
                        ):
                    for subregion in subregions:
                        self.blockCounts[subregion.samtoolsStr()] = {
                            "name": subregion.name, 
                            "str": subregion.samtoolsStr(), 
                            "Aseq": 0, 
                            "A>T": 0,
                            "A>C": 0,
                            "A>G": 0,
                            "Tseq": 0,
                            "T>A": 0,
                            "T>C": 0,
                            "T>G": 0,
                            "Cseq": 0,
                            "C>A": 0,
                            "C>T": 0,
                            "C>G": 0,
                            "Gseq": 0,
                            "G>A": 0,
                            "G>T": 0,
                            "G>C": 0,
                            "ins":defaultdict(int),
                            "dels": defaultdict(int),
                            "DP": 0
                            }
                
                for pileup_column in self.inBam.pileup(
                        reference=myRegion.chrom, 
                        start=myRegion.startPos , 
                        end=myRegion.endPos,
                        fastafile=self.inFasta, 
                        truncate=True, 
                        stepper="nofilter", 
                        max_depth=1000000, 
                        min_base_quality = 0
                        ):
                    myChrPos = f"{myRegion.chrom}:{pileup_column.reference_pos + 1}"
                    lnCnts = self.CountLine(
                        pileup_column, 
                        roundLevel,
                        self.params["unique"],
                        self.params["Nprop"], 
                        self.params["minDepth"], 
                        self.params["minC"], 
                        self.params["maxC"]
                        )
                    self.geneCounts[regStr]["DP"] += lnCnts["DP"]
                    self.geneCounts[regStr][f"{lnCnts['RefBase']}seq"] += lnCnts["DP"]
                    
                    for xIter in ("A","C","G","T"):
                        if xIter != lnCnts["RefBase"]:
                            self.geneCounts[regStr][f"{lnCnts['RefBase']}>{xIter}"] += lnCnts[xIter]
                    for xIter in lnCnts["ins"]:
                        self.geneCounts[regStr]["ins"][xIter] += lnCnts["ins"][xIter]
                    for xIter in lnCnts["dels"]:
                        self.geneCounts[regStr]["dels"][xIter] += lnCnts["dels"][xIter]
                    
                    if not ( 
                            len(subregions) == 1
                            and subregions[0].startPos == myRegion.startPos
                            and subregions[0].endPos == myRegion.endPos
                            ):
                        for subregion in subregions:
                            if subregion.contains(myRegion.chrom, pileup_column.reference_pos):
                                self.blockCounts[subregion.samtoolsStr()]["DP"] += lnCnts["DP"]
                                self.blockCounts[subregion.samtoolsStr()][f"{lnCnts['RefBase']}seq"] += lnCnts["DP"]
                                
                                for xIter in ("A","C","G","T"):
                                    if xIter != lnCnts["RefBase"]:
                                        self.blockCounts[subregion.samtoolsStr()][f"{lnCnts['RefBase']}>{xIter}"] += lnCnts[xIter]
                                for xIter in lnCnts["ins"]:
                                    self.blockCounts[subregion.samtoolsStr()]["ins"][xIter] += lnCnts["ins"][xIter]
                                for xIter in lnCnts["dels"]:
                                    self.blockCounts[subregion.samtoolsStr()]["dels"][xIter] += lnCnts["dels"][xIter]
                    if myChrPos not in linesCounted:
                        linesCounted.append(myChrPos)
                        self.mutsCounts["DP"] += lnCnts["DP"]
                        self.mutsCounts[f"{lnCnts['RefBase']}seq"] += lnCnts["DP"]
                        
                        for xIter in ("A","C","G","T"):
                            if xIter != lnCnts["RefBase"]:
                                self.mutsCounts[f"{lnCnts['RefBase']}>{xIter}"] += lnCnts[xIter]
                        for xIter in lnCnts["ins"]:
                            self.mutsCounts["ins"][xIter] += lnCnts["ins"][xIter]
                        for xIter in lnCnts["dels"]:
                            self.mutsCounts["dels"][xIter] += lnCnts["dels"][xIter]
                        
                        linesProcessed += 1
                        if linesProcessed % 1000 == 0:
                            logging.info(f"{linesProcessed} lines processed...")
                    
    
    def CountLine(self, 
                  pileup_column, 
                  roundLevel = 4, 
                  unique=False, 
                  Nprop=1, 
                  minDepth=1, 
                  minC=0, 
                  maxC=1
                  ):
        myReads = Counter(
            [x.upper() 
                for x in pileup_column.get_query_sequences(
                    add_indels=True
                    )
                ]
            )
        
        mReads = defaultdict(int)

        # myReads should be something like
        myChrom = pileup_column.reference_name
        myPos = pileup_column.reference_pos + 1
        # I'll need to pull the reference base from the fasta file
        
        myRefBase = self.inFasta.fetch(reference=myChrom, start=myPos-1, end=myPos).upper()
        logging.debug(f"Refernce is: {myRefBase}")
        myNCount = sum([myReads[x] for x in myReads if x[0] == "N"])
        myTotCount = sum([myReads[x] for x in myReads])
        clonalities = {x: myReads[x]/(myTotCount - myNCount) if myTotCount - myNCount > 0 else 0 for x in myReads}
        for x in myReads:
            if clonalities[x] >= minC and clonalities[x] <= maxC:
                if unique:
                    mReads[x] = 1
                else:
                    mReads[x] = myReads[x]
        if (
                myNCount / myTotCount <= Nprop and 
                myTotCount >= minDepth
                ):
            
            mutsDict = {"RefBase": myRefBase, 
                        "A": mReads["A"], 
                        "C": mReads["C"], 
                        "G": mReads["G"], 
                        "T": mReads["T"], 
                        "ins": defaultdict(int), 
                        "dels": defaultdict(int), 
                        "DP": myTotCount-myNCount
                        }
            for readTypeKey in mReads:
                if readTypeKey != "*":
                    if '-' in readTypeKey:
                        myRefBPs = self.inFasta.fetch(reference=myChrom, start=myPos-1, end=myPos+len(readTypeKey[2:])).upper()
                        if 'N' not in myRefBPs:
                            mutsDict["dels"][''.join(c for c in readTypeKey[1:] if c.isdigit())] += mReads[readTypeKey]
                    elif '+' in readTypeKey:
                        if 'N' not in readTypeKey:
                            mutsDict["ins"][''.join(c for c in readTypeKey[1:] if c.isdigit())] += mReads[readTypeKey]
        else:
            mutsDict = {"RefBase": myRefBase, 
                        "A": 0, 
                        "C": 0, 
                        "G": 0, 
                        "T": 0, 
                        "ins": defaultdict(int), 
                        "dels": defaultdict(int), 
                        "DP": 0
                        }
        return(mutsDict)
    
    def genSummary(self, Fout, overall_mode="GENES", gene_mode="FULL", outputs="GB"):
        logging.debug("Generating summary")
        logging.debug(self.mutsCounts)
        logging.debug(self.geneCounts)
        logging.debug(self.blockCounts)
        self.subregCounts = {}
        subregNum = 0
        subregNames = [x for x in self.blockCounts]
        
        outFile = open(Fout, 'w')
        outFile.write(
            f"##CountMuts output:\n"
            f"##Input file: \t{self.params['inBam']}\n"
            f"##Input reference:\t{self.params['inFasta']}\n"
            f"##Input bed:\t{self.params['inBed']}\n"
            f"##Minimum Depth: \t{self.params['minDepth']}\n"
            f"##Clonality: \t{self.params['minC']}-{self.params['maxC']}\n"
            )
        if overall_mode == "GENES":
            outFile.write(
                f"##OVERAL = Sum of Genes\n"
                )
            overall_counts = self.mutsCounts
        elif overall_mode == "BLOCKS":
            outFile.write(
                f"##OVERALL = Sum of Blocks\n"
                )
            overall_counts = {
                "Aseq": sum([self.blockCounts[x]["Aseq"] for x in self.blockCounts]), 
                "A>T": sum([self.blockCounts[x]["A>T"] for x in self.blockCounts]),
                "A>C": sum([self.blockCounts[x]["A>C"] for x in self.blockCounts]),
                "A>G": sum([self.blockCounts[x]["A>G"] for x in self.blockCounts]),
                "Tseq": sum([self.blockCounts[x]["Tseq"] for x in self.blockCounts]),
                "T>A": sum([self.blockCounts[x]["T>A"] for x in self.blockCounts]),
                "T>C": sum([self.blockCounts[x]["T>C"] for x in self.blockCounts]),
                "T>G": sum([self.blockCounts[x]["T>G"] for x in self.blockCounts]),
                "Cseq": sum([self.blockCounts[x]["Cseq"] for x in self.blockCounts]),
                "C>A": sum([self.blockCounts[x]["C>A"] for x in self.blockCounts]),
                "C>T": sum([self.blockCounts[x]["C>T"] for x in self.blockCounts]),
                "C>G": sum([self.blockCounts[x]["C>G"] for x in self.blockCounts]),
                "Gseq": sum([self.blockCounts[x]["Gseq"] for x in self.blockCounts]),
                "G>A": sum([self.blockCounts[x]["G>A"] for x in self.blockCounts]),
                "G>T": sum([self.blockCounts[x]["G>T"] for x in self.blockCounts]),
                "G>C": sum([self.blockCounts[x]["G>C"] for x in self.blockCounts]),
                "ins":Counter(),
                "dels": Counter(),
                "DP": sum([self.blockCounts[x]["DP"] for x in self.blockCounts])
                }
            for x in self.blockCounts:
                overall_counts["ins"].update(self.blockCounts[x]["ins"])
                overall_counts["dels"].update(self.blockCounts[x]["dels"])
                
        else:
            logging.error(f"Invalid overlap mode: {overall_mode}")
            raise Exception()
        subregNum = 0
        subregNames = [x for x in self.blockCounts]
        if gene_mode == "FULL":
            outFile.write(
                f"##GENE = Total\n"
                )
            gene_counts = self.geneCounts
        elif gene_mode == "BLOCKS":
            outFile.write(
                f"##GENE = Sum of Blocks\n"
                )
            gene_counts = {}
            for geneIter in self.geneCounts:
                gene_counts[geneIter] = {
                    "name": self.geneCounts[geneIter]["name"], 
                    "str": self.geneCounts[geneIter]["str"], 
                    "Aseq": 0, 
                    "A>T": 0,
                    "A>C": 0,
                    "A>G": 0,
                    "Tseq": 0,
                    "T>A": 0,
                    "T>C": 0,
                    "T>G": 0,
                    "Cseq": 0,
                    "C>A": 0,
                    "C>T": 0,
                    "C>G": 0,
                    "Gseq": 0,
                    "G>A": 0,
                    "G>T": 0,
                    "G>C": 0,
                    "ins":defaultdict(int),
                    "dels": defaultdict(int),
                    "DP": 0, 
                    "blocks":self.geneCounts[geneIter]["blocks"]
                    }
                for subregIter in range(self.geneCounts[geneIter]["blocks"]):
                    gene_counts[geneIter]["Aseq"] += self.blockCounts[subregNames[subregNum]]["Aseq"]
                    gene_counts[geneIter]["A>T"]  += self.blockCounts[subregNames[subregNum]]["A>T"]
                    gene_counts[geneIter]["A>C"]  += self.blockCounts[subregNames[subregNum]]["A>C"]
                    gene_counts[geneIter]["A>G"]  += self.blockCounts[subregNames[subregNum]]["A>G"]
                    gene_counts[geneIter]["Tseq"] += self.blockCounts[subregNames[subregNum]]["Tseq"]
                    gene_counts[geneIter]["T>A"]  += self.blockCounts[subregNames[subregNum]]["T>A"]
                    gene_counts[geneIter]["T>C"]  += self.blockCounts[subregNames[subregNum]]["T>C"]
                    gene_counts[geneIter]["T>G"]  += self.blockCounts[subregNames[subregNum]]["T>G"]
                    gene_counts[geneIter]["Cseq"] += self.blockCounts[subregNames[subregNum]]["Cseq"]
                    gene_counts[geneIter]["C>A"]  += self.blockCounts[subregNames[subregNum]]["C>A"]
                    gene_counts[geneIter]["C>T"]  += self.blockCounts[subregNames[subregNum]]["C>T"]
                    gene_counts[geneIter]["C>G"]  += self.blockCounts[subregNames[subregNum]]["C>G"]
                    gene_counts[geneIter]["Gseq"] += self.blockCounts[subregNames[subregNum]]["Gseq"]
                    gene_counts[geneIter]["G>A"]  += self.blockCounts[subregNames[subregNum]]["G>A"]
                    gene_counts[geneIter]["G>T"]  += self.blockCounts[subregNames[subregNum]]["G>T"]
                    gene_counts[geneIter]["G>C"]  += self.blockCounts[subregNames[subregNum]]["G>C"]
                    gene_counts[geneIter]["DP"] += self.blockCounts[subregNames[subregNum]]["DP"]
                    gene_counts[geneIter]["ins"].update(self.blockCounts[subregNames[subregNum]]["ins"])
                    gene_counts[geneIter]["dels"].update(self.blockCounts[subregNames[subregNum]]["dels"])
                    subregNum += 1
        else:
            logging.error(f"Invalid gene mode: {gene_mode}")
            raise Exception()
        
        self.subregCounts = {}
        subregNum = 0
        for geneIter in gene_counts:
            if "G" in outputs:
                self.subregCounts[geneIter] = gene_counts[geneIter]
            if "B" in outputs:
                for subregIter in range(gene_counts[geneIter]["blocks"]):
                    self.subregCounts[subregNames[subregNum]] = self.blockCounts[subregNames[subregNum]]
                    subregNum += 1
                
        
        if self.params["unique"]:
            outFile.write(
                "##Unique mutations only\n"
                )
        outFile.write("#SAMPLE,REGION,MUTATION_TYPE,MUTATION_CLASS,COUNT,DENOMINATOR,FREQUENCY\n")
        # Overall Output:
        totPointMuts = 0

        for x in ("A","T","C","G"):
            for y in ("A","T","C","G"):
                if x != y:
                    wilsonCI = Wilson(
                        overall_counts[f"{x}>{y}"],  
                        max(overall_counts[f"{x}seq"], 1)
                        )
                    totPointMuts += overall_counts[f'{x}>{y}']
                    outFile.write(
                        f"{self.sample},"
                        f"OVERALL,{x}>{y},SNV,"
                        f"{overall_counts[f'{x}>{y}']},"
                        f"{overall_counts[f'{x}seq']},"
                        f"{wilsonCI[0]:.2e}\n"
                        )
        
        wilsonCI = Wilson(totPointMuts, max(overall_counts['DP'], 1))
        
        outFile.write(
            f"{self.sample},"
            f"OVERALL,Total,SNV,"
            f"{totPointMuts},"
            f"{overall_counts['DP']},"
            f"{wilsonCI[0]:.2e}\n"
            )
        
        # insertions:
        if overall_counts['ins'] != {}:
            insKeys = sorted(int(x) for x in overall_counts['ins'])
            for n in insKeys:
                if overall_counts['ins'][str(n)] != 0:
                    wilsonCI = Wilson(
                        overall_counts['ins'][str(n)], 
                        max(overall_counts['DP'], 1)
                        )
                    outFile.write(
                        f"{self.sample},"
                        f"OVERALL,+{n},INS,{overall_counts['ins'][str(n)]},"
                        f"{overall_counts['DP']},"
                        f"{wilsonCI[0]:.2e}\n"
                        )
            totIns = sum([overall_counts['ins'][x] for x in overall_counts['ins']])
            wilsonCI = Wilson(
                totIns, 
                max(overall_counts['DP'], 1)
                )
            outFile.write(
                f"{self.sample},"
                f"OVERALL,Total,INS,{totIns},"
                f"{overall_counts['DP']},"
                f"{wilsonCI[0]:.2e}\n"
                )
        if self.mutsCounts['dels'] != {}:
            delsKeys = sorted(int(x) for x in overall_counts['dels'])
            for n in delsKeys:
                if overall_counts['dels'][str(n)] != 0:
                    wilsonCI = Wilson(
                        overall_counts['dels'][str(n)], 
                        max(overall_counts['DP'], 1)
                        )
                    outFile.write(
                        f"{self.sample},"
                        f"OVERALL,-{n},DEL,{overall_counts['dels'][str(n)]},"
                        f"{overall_counts['DP']},"
                        f"{wilsonCI[0]:.2e}\n"
                        )
            totDels = sum([overall_counts['dels'][x] for x in overall_counts['dels']])
            wilsonCI = Wilson(
                totDels, 
                max(overall_counts['DP'], 1)
                )
            outFile.write(
                f"{self.sample},"
                f"OVERALL,Total,DEL,{totDels},"
                f"{overall_counts['DP']},"
                f"{wilsonCI[0]:.2e}\n"
                )
                
        # Detail counts:
        for subreg in self.subregCounts:
            totPointMuts = 0
            for x in ("A","T","C","G"):
                for y in ("A","T","C","G"):
                    if x != y:
                        wilsonCI = Wilson(
                            self.subregCounts[subreg][f"{x}>{y}"],  
                            max(self.subregCounts[subreg][f"{x}seq"], 1)
                            )
                        totPointMuts += self.subregCounts[subreg][f'{x}>{y}']
                        outFile.write(
                            f"{self.sample},"
                            f"{self.subregCounts[subreg]['name']},"
                            f"{x}>{y},SNV,"
                            f"{self.subregCounts[subreg][f'{x}>{y}']},"
                            f"{self.subregCounts[subreg][f'{x}seq']},"
                            f"{wilsonCI[0]:.2e}\n"
                            )
            
            wilsonCI = Wilson(totPointMuts, max(self.subregCounts[subreg]['DP'], 1))
            outFile.write(
                f"{self.sample},"
                f"{self.subregCounts[subreg]['name']},"
                f"Total,SNV,"
                f"{totPointMuts},"
                f"{self.subregCounts[subreg]['DP']},"
                f"{wilsonCI[0]:.2e}\n"
                )
            
            # insertions:
            if self.subregCounts[subreg]['ins'] != {}:
                insKeys = sorted(int(x) for x in self.subregCounts[subreg]['ins'])
                for n in insKeys:
                    if self.subregCounts[subreg]['ins'][str(n)] != 0:
                        wilsonCI = Wilson(
                            self.subregCounts[subreg]['ins'][str(n)], 
                            max(self.subregCounts[subreg]['DP'], 1)
                            )
                        outFile.write(
                            f"{self.sample},"
                            f"{self.subregCounts[subreg]['name']},"
                            f"+{n},INS,{self.subregCounts[subreg]['ins'][str(n)]},"
                            f"{self.subregCounts[subreg]['DP']},"
                            f"{wilsonCI[0]:.2e}\n"
                            )
                totIns = sum([self.subregCounts[subreg]['ins'][x] for x in self.subregCounts[subreg]['ins']])
                wilsonCI = Wilson(
                    totIns, 
                    max(self.subregCounts[subreg]['DP'], 1)
                    )
                outFile.write(
                    f"{self.sample},"
                    f"{self.subregCounts[subreg]['name']},"
                    f"Total,INS,{totIns},"
                    f"{self.subregCounts[subreg]['DP']},"
                    f"{wilsonCI[0]:.2e}\n"
                    )
            if self.subregCounts[subreg]['dels'] != {}:
                delsKeys = sorted(int(x) for x in self.subregCounts[subreg]['dels'])
                for n in delsKeys:
                    if self.subregCounts[subreg]['dels'][str(n)] != 0:
                        wilsonCI = Wilson(
                            self.subregCounts[subreg]['dels'][str(n)], 
                            max(self.subregCounts[subreg]['DP'], 1)
                            )
                        outFile.write(
                            f"{self.sample},"
                            f"{self.subregCounts[subreg]['name']},"
                            f"+{n},DEL,{self.subregCounts[subreg]['dels'][str(n)]},"
                            f"{self.subregCounts[subreg]['DP']},"
                            f"{wilsonCI[0]:.2e}\n"
                            )
                totDels = sum([self.subregCounts[subreg]['dels'][x] for x in self.subregCounts[subreg]['dels']])
                wilsonCI = Wilson(
                    totDels, 
                    max(self.subregCounts[subreg]['DP'], 1)
                    )
                outFile.write(
                    f"{self.sample},"
                    f"{self.subregCounts[subreg]['name']},"
                    f"Total,DEL,{totDels},"
                    f"{self.subregCounts[subreg]['DP']},"
                    f"{wilsonCI[0]:.2e}\n"
                    )
                    
        outFile.close()

def main():
    o = getParams()
    if 'N' in o.outType:
        o.outType = ""
    if o.sumType[0] == "G":
        o.overallSum = "GENES"
    elif o.sumType[0] == "B":
        o.overallSum = "BLOCKS"
    else:
        raise Exception()
    if o.sumType[1] == "T":
        o.geneSum = "FULL"
    elif o.sumType[1] == "B":
        o.geneSum = "BLOCKS"
    else:
        raise Exception()
    numeric_level = getattr(logging, o.logLvl.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError('Invalid log level: {o.logLvl}')
    logging.basicConfig(
        format='%(levelname)s: %(message)s', 
        level=numeric_level, 
        )
    # Start engine
    logging.info("Starting Engine")
    myEngine = countMutsEngine(
        o.inBam, 
        o.in_fasta, 
        o.inBed, 
        o.unique,
        o.n_cutoff, 
        o.mindepth, 
        o.min_clonality, 
        o.max_clonality, 
        o.sampName
        )
    logging.info("Processing Lines")
    myEngine.processLines(
        o.round
        )
    myEngine.genSummary(
        Fout=o.out_file,
        overall_mode=o.overallSum,
        gene_mode=o.geneSum,
        outputs=o.outType
        )
            
            
if __name__ == "__main__":
    main()
