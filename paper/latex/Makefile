# Build the iacrj LaTeX port of the paper.
#
#   make          - full build: pdflatex, bibtex, pdflatex, pdflatex
#   make clean    - remove build artifacts (keeps the .pdf)
#   make distclean - remove build artifacts AND the .pdf

NAME = sdbkz_paper_latex
AUX  = $(NAME).aux $(NAME).log $(NAME).out $(NAME).toc $(NAME).meta \
       $(NAME).bbl $(NAME).blg

.PHONY: all clean distclean

all: $(NAME).pdf

$(NAME).pdf: $(NAME).tex crypto.bib biblio.bib abbrev3.bib
	pdflatex -interaction=nonstopmode $(NAME).tex
	bibtex $(NAME)
	pdflatex -interaction=nonstopmode $(NAME).tex
	pdflatex -interaction=nonstopmode $(NAME).tex
	@rm -f $(AUX)

clean:
	rm -f $(AUX)

distclean: clean
	rm -f $(NAME).pdf
