args = commandArgs(trailingOnly=TRUE)

inBed = args[1]
inSampName = args[2]
inSampType = args[3]
bedLinesPerImage = 1
library(ggplot2)
library(readr)
print("Loaded libraries")
addZeros <- function(inData) {
  #column labels: #Chrom  Pos Ref DP  Ns
  outChroms = c()
  outPos = c()
  outRef = c()
  outDp = c()
  outNs = c()
  contiguousStart = 1
  contiguousEnd = 1
  for (datIter in seq(1,length(row.names(inData)))) {
    if ( inData$`#Chrom`[datIter] == inData$`#Chrom`[contiguousStart] &&
         inData$`Pos`[datIter] == inData$`Pos`[contiguousStart] + datIter - contiguousStart
    ) {
      contiguousEnd = datIter
    } else {
      outChroms = c(outChroms, 
                    inData$`#Chrom`[contiguousStart], 
                    inData$`#Chrom`[contiguousStart:contiguousEnd], 
                    inData$`#Chrom`[datIter-1]
      )
      outPos = c(outPos, 
                 inData$Pos[contiguousStart] - 1, 
                 inData$Pos[contiguousStart:contiguousEnd], 
                 inData$Pos[contiguousEnd] + 1
      )
      outRef = c(outRef, 
                 '.', 
                 inData$Ref[contiguousStart:contiguousEnd], 
                 '.'
      )
      outDp = c(outDp, 
                0, 
                inData$DP[contiguousStart:contiguousEnd], 
                0
      )
      outNs = c(outNs, 
                0, 
                inData$Ns[contiguousStart:contiguousEnd], 
                0
      )
      contiguousStart = datIter
      contiguousEnd = datIter
    }
  }
  outChroms = c(outChroms, 
                inData$`#Chrom`[contiguousStart], 
                inData$`#Chrom`[contiguousStart:contiguousEnd], 
                inData$`#Chrom`[datIter-1]
                )
  outPos = c(outPos, 
             inData$Pos[contiguousStart] - 1, 
             inData$Pos[contiguousStart:contiguousEnd], 
             inData$Pos[contiguousEnd] + 1
             )
  outRef = c(outRef, 
             '.', 
             inData$Ref[contiguousStart:contiguousEnd], 
             '.'
             )
  outDp = c(outDp, 
            0, 
            inData$DP[contiguousStart:contiguousEnd], 
            0
            )
  outNs = c(outNs, 
            0, 
            inData$Ns[contiguousStart:contiguousEnd], 
            0
            )
  outData = data.frame(`Chrom` = outChroms, Pos = outPos, Ref = outRef, DP = outDp, Ns = outNs)
  return(outData)
}
# read in bed file
# input:
#        inBed = get_target_bed,
#        inDepth = "{runPath}/Stats/data/{sample}.{sampType}.region.mutpos.vcf_depth.txt",

#    output:
#        "{runPath}/Stats/plots/{sample}.{sampType}.targetCoverage.png"

myBed <- read_table(inBed, col_names = FALSE)
myFName = paste("Stats/data/",inSampName, ".depth.txt", sep="")
pre_depth <- read_delim(myFName,
                    "\t", escape_double = FALSE, trim_ws = TRUE, 
                    col_types="cicii")
if (length(row.names(pre_depth)) > 0) {
  depth <- addZeros(pre_depth)
} else {
  depth <- pre_depth
}
# Set column names
bedColNames = c("Chrom","Start","End", "Name","Score","Strand","thickStart","thickEnd","itemRgb","blockCounts","blockSizes","blockStarts")
numCols = length(colnames(myBed))
colnames(myBed) <- bedColNames[1:numCols]
print("Loaded bed")
myBed$Start <- myBed$Start + 1
myBed$End <- myBed$End + 1
myBed$Target = factor(myBed$Name, levels = c(myBed$Name,"Off_Target"))
namesVect = c()

# Get targets and compute maximum depth / Ns for each bed region

multCalc = data.frame(Name = myBed$Name, 
  maxDepth=replicate(length(row.names(myBed)),1), 
  maxNs=replicate(length(row.names(myBed)),1)
  )

if (length(row.names(depth)) > 0) {
  for (dataIter in seq(1,length(row.names(depth)))) {
    myName = "Off_Target"
    for (bedIter in seq(1, length(row.names(myBed)))) {
      if ( depth$Chrom[dataIter] == myBed$Chrom[bedIter] && 
           depth$Pos[dataIter] >= myBed$Start[bedIter] && 
           depth$Pos[dataIter] < myBed$End[bedIter]) {
        myName = myBed$Name[bedIter]
        multCalc$maxDepth[bedIter] = max(multCalc$maxDepth[bedIter], depth$DP[dataIter])
        multCalc$maxNs[bedIter] = max(multCalc$maxNs[bedIter], depth$Ns[dataIter])
        break
      }
    }
    namesVect = c(namesVect, myName)
  }
  maxDP = max(depth$DP)
  depth$Nfract = depth$Ns / depth$DP * 100
  depth$Nfract[depth$DP == 0] = 0
  multCalc$maxNs = ceiling(multCalc$maxNs/3)*3
} else {
  depth$Target = factor(namesVect, levels = c(myBed$Name,"Off_Target"))
}
depth$Target = factor(namesVect, levels = c(myBed$Name,"Off_Target"))
multCalc$multiplier = -multCalc$maxDepth / multCalc$maxNs

print("processed depth and VCF")

numRegions <- length(levels(depth$Target))-1
numPages <- ceiling(numRegions / bedLinesPerImage)

myFName = paste("Final/",inSampType,"/",inSampName, ".vcf", sep="")
myVCF <- read_delim(
  myFName, "\t", 
  escape_double = FALSE, 
  comment = "##", 
  trim_ws = TRUE
)
namesVect = c()
if (length(row.names(myVCF)) > 0) {
  for (dataIter in seq(1,length(row.names(myVCF)))) {
    myName = "Off_Target"
    for (bedIter in seq(1, length(row.names(myBed)))) {
      if ( myVCF$`#CHROM`[dataIter] == myBed$Chrom[bedIter] && 
           myVCF$POS[dataIter] >= myBed$Start[bedIter] && 
           myVCF$POS[dataIter] < myBed$End[bedIter]) {
        myName = myBed$Name[bedIter]
        break
      }
    }
    namesVect = c(namesVect, myName)
  }
  myVCF$Target = factor(namesVect, levels = c(myBed$Name,"Off_Target"))
} else {myVCF$Target = factor()}
 

for (pageIter in seq(1,numPages)) {
  print(paste(pageIter,numPages,sep="/"))
  if (pageIter == 1) {
    minIndex <- 1
    maxIndex <- pageIter * bedLinesPerImage
  } else {
    minIndex <- (pageIter - 1) * bedLinesPerImage + 1
    maxIndex <- pageIter * bedLinesPerImage
  }
  maxDP = max(multCalc$maxDepth[multCalc$Name %in% myBed$Name[minIndex:maxIndex]])
  maxNs = max(multCalc$maxNs[multCalc$Name %in% myBed$Name[minIndex:maxIndex]])
  multiplier = -maxDP / maxNs
  print(myBed$Name[minIndex:maxIndex])
  myPlot=ggplot(data = depth[depth$Target %in% myBed$Name[minIndex:maxIndex],]) + 
    geom_area(mapping = aes(x = Pos, y = DP), stat="identity") + 
    geom_area(mapping=aes(x=Pos, y=Ns * multiplier), color='red', fill='red', alpha=0.7, stat="identity") + 
    geom_segment(data = myBed[minIndex:maxIndex,], mapping = aes(x=Start,xend=End, y=0, yend=0))
  if (length(row.names(myVCF[myVCF$Target %in% myBed$Name[minIndex:maxIndex],])) > 0) {
    myPlot = myPlot + 
      geom_point(data=myVCF[myVCF$Target %in% myBed$Name[minIndex:maxIndex],], mapping=aes(x=POS, y=maxDP), shape=1)
  }
  if (pageIter == 1) {
    myPlot = myPlot + labs(title = inSampName)
  } else {
    myPlot = myPlot + labs(title = "")
  }
  myPlot = myPlot + 
    scale_y_continuous(
      name="Depth", 
      breaks = c(0, maxDP), 
      sec.axis = sec_axis(~./multiplier, name="Ns (count)", breaks = c(0,maxNs/3, 2*maxNs/3,maxNs), labels = c(0,maxNs/3, 2*maxNs/3,maxNs))) + 
    theme_bw() + xlab("Genome Position") + 
    theme(
      axis.title.y.right = element_text(color='red'), 
      axis.text.x = element_text(angle=90), 
    ) + 
    facet_wrap(. ~ Target, scales = "free_x", ncol = 1)
ggsave(filename = paste("Stats/plots/", inSampName, ".", pageIter, 
                        ".targetCoverage.png", sep=""), 
       plot = myPlot, 
       width = 200, 
       height = 60*bedLinesPerImage, 
       units="mm", 
       device = "png", 
       limitsize=FALSE
       )
}
