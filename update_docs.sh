#!/bin/bash

for nb in *.ipynb; do
	echo "updating docs from ${nb}"
	jupyter nbconvert --to markdown --no-input "${nb}"
	md="${nb%%.ipynb}"
	sed -i 's/^\ \ \ \ //g' "${md}.md"
done
