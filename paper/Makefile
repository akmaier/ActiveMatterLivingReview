LATEXMK = latexmk -pdf -interaction=nonstopmode -halt-on-error

.PHONY: paper proposal clean

paper:
	$(LATEXMK) main.tex

proposal:
	cd proposal && $(LATEXMK) proposal.tex

clean:
	latexmk -C main.tex
	cd proposal && latexmk -C proposal.tex
