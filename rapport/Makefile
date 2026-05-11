# Compilation du rapport TER M1
# Cible par defaut : pdflatex + bibtex + 2 passes

MAIN := main
LATEX := pdflatex -interaction=nonstopmode -halt-on-error

.PHONY: all clean distclean view

all: $(MAIN).pdf

$(MAIN).pdf: $(MAIN).tex chapitres/*.tex biblio.bib garde.tex tikz_styles.tex figures/*.tex
	$(LATEX) $(MAIN).tex
	-biber $(MAIN)
	$(LATEX) $(MAIN).tex
	$(LATEX) $(MAIN).tex

view: $(MAIN).pdf
	@command -v xdg-open >/dev/null && xdg-open $(MAIN).pdf || echo "Ouvre $(MAIN).pdf manuellement."

clean:
	rm -f *.aux *.log *.toc *.lof *.lot *.bbl *.blg *.bcf *.run.xml \
	      *.out *.synctex.gz chapitres/*.aux

distclean: clean
	rm -f $(MAIN).pdf
