#!/usr/bin/env Rscript
# Base-R figures consume the production count table; they never read or change H5AD.
a <- commandArgs(trailingOnly=TRUE)
if(length(a)!=2L) stop("Usage: plot_composition.R COUNTS.tsv NEW_FIGURE_DIRECTORY")
d <- read.delim(a[1], check.names=FALSE, stringsAsFactors=FALSE,
                colClasses=c(sample_id="character",cell_type="character"), na.strings="")
required <- c("sample_id","cell_type","count","denominator","proportion")
stopifnot(all(required %in% names(d)), nrow(d)>0, !anyDuplicated(d[c("sample_id","cell_type")]),
          !anyNA(d$sample_id), !anyNA(d$cell_type),
          all(is.finite(d$count)), all(d$count>=0), all(d$count==floor(d$count)))
samples <- sort(unique(d$sample_id)); types <- sort(unique(d$cell_type))
stopifnot(nrow(d)==length(samples)*length(types))
counts <- matrix(0,length(types),length(samples),dimnames=list(types,samples))
counts[cbind(match(d$cell_type,types),match(d$sample_id,samples))] <- d$count
n <- colSums(counts)
stopifnot(all(d$denominator==n[match(d$sample_id,samples)]))
prop <- sweep(counts,2,n,"/");prop[,n==0] <- NA_real_
stopifnot(all(abs(d$proportion-prop[cbind(match(d$cell_type,types),match(d$sample_id,samples))])<1e-10,na.rm=TRUE),
          all(is.na(d$proportion)==is.na(prop[cbind(match(d$cell_type,types),match(d$sample_id,samples))])))
if(dir.exists(a[2])) stop("Figure directory already exists")
dir.create(a[2],recursive=TRUE); out <- normalizePath(a[2])
colors <- setNames(hcl.colors(length(types),"Dark 3"),types)
colors[grepl("Unknown|missing",names(colors),ignore.case=TRUE)] <- "#9CA3AF"
write.table(data.frame(cell_type=types,color=colors),file.path(out,"legend.tsv"),sep="\t",quote=FALSE,row.names=FALSE)
# Horizontal bars keep core labels readable; n exposes each denominator.
draw_bars <- function(){
    layout(matrix(c(1,2),1),widths=c(3,1.5))
    par(mar=c(4,10,3,1),cex=.85)
    p <- prop[,rev(samples),drop=FALSE];p[is.na(p)]<-0
    barplot(p,horiz=TRUE,col=colors,border=NA,las=1,xlim=c(0,1),
            names.arg=paste0(rev(samples), "  (n=",n[rev(samples)],")"),xlab="Fraction of retained cells",main="Cell-type composition by observation")
    par(mar=c(4,0,3,1));plot.new();legend("topleft",legend=types,fill=colors,border=NA,bty="n",cex=.85)
    mtext("Descriptive proportions by observation",side=1,line=2,cex=.8)
    if(any(n==0)) mtext("n=0: composition undefined",side=1,line=3,cex=.8)
}
height <- max(6,1.7+.19*length(samples))
pdf(file.path(out,"composition.pdf"),width=12,height=height,useDingbats=FALSE);draw_bars();dev.off()
png(file.path(out,"composition.png"),width=1800,height=round(height*150),res=150);draw_bars();dev.off()
# Heatmap uses a common 0-100% scale, preserving absolute proportions.
draw_heat <- function(){
    layout(matrix(c(1,2),1),widths=c(12,1.5))
    par(mar=c(10,max(7,max(nchar(types))*.48),4,1),cex=.8)
    palette <- hcl.colors(100,"YlGnBu",rev=TRUE)
    z<-t(prop[rev(types),,drop=FALSE])
    image(seq_along(samples),seq_along(types),z,zlim=c(0,1),col=palette,axes=FALSE,xlab="",ylab="",main="Cell-type composition by observation")
    if(any(n==0)) for(j in which(n==0)) rect(j-.5,.5,j+.5,length(types)+.5,col="#D1D5DB",border=NA)
    axis(1,at=seq_along(samples),labels=ifelse(n==0,paste0(samples," (n=0)"),samples),las=2,cex.axis=.7)
    axis(2,at=seq_along(types),labels=rev(types),las=1,cex.axis=.8)
    par(mar=c(10,0,4,4)); image(1,seq(0,1,length.out=100),matrix(seq(0,1,length.out=100),1),col=palette,axes=FALSE,xlab="",ylab="")
    axis(4,at=seq(0,1,.25),labels=paste0(seq(0,100,25),"%"),las=1)
    mtext("Retained-cell fraction",side=4,line=3)
    if(any(n==0)) mtext("Gray: n=0",side=1,line=2,cex=.8)
}
pdf(file.path(out,"heatmap.pdf"),width=max(10,length(samples)*.2),height=max(6,length(types)*.22+3),useDingbats=FALSE);draw_heat();dev.off()
write.table(data.frame(sample_id=samples,retained_cells=n),file.path(out,"denominators.tsv"),sep="\t",quote=FALSE,row.names=FALSE)
writeLines(c("Counts and proportions validated against plotted matrix.","Figures are descriptive; no statistical group tests.",capture.output(sessionInfo())),file.path(out,"verification.txt"))
