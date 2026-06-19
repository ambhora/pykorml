# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: CC-BY-4.0
# Copyright (C) 2025 Jayesh Badwaik <j.badwaik@fz-juelich.de>
# --------------------------------------------------------------------------------------------------
DOCTITLE=paper
# Temporary directories for build files
BUILDIR=tmp/build

# Suppress output from build step to keep the console clean
.SILENT: debug

# Define the flags for the document build process
BFLAGS_FINAL=-bibtex -lualatex

# Define the flags for the document build process in fixme mode
BFLAGS=-bibtex -lualatex

# Define the flags for latexmk to run in quiet mode and with specific options
IFLAGS=-quiet -interaction=nonstopmode -logfilewarnings- -shell-escape -gg -cd

# Main target to build the document
all: draft

# Target to build the document with latexmk
draft:	${DOCTITLE}.tex
	mkdir -p ${BUILDIR}
	latexmk \
		-outdir=${BUILDIR} -auxdir=${BUILDIR} \
		${BFLAGS} ${IFLAGS}	${DOCTITLE}.tex
	cp ${BUILDIR}/${DOCTITLE}.pdf ${DOCTITLE}.pdf


# Target to build the document with latexmk
final:	${DOCTITLE}.tex
	mkdir -p ${BUILDIR}
	latexmk \
		-outdir=${BUILDIR} -auxdir=${BUILDIR} \
		${BFLAGS_FINAL} ${IFLAGS}	${DOCTITLE}.tex
	cp ${BUILDIR}/${DOCTITLE}.pdf ${DOCTITLE}.pdf

# Target to clean up build files
clean:
	rm -r ${BUILDIR} ${DOCTITLE}.pdf

