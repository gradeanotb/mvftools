.. _intro:

###############
Getting Started
###############

What is MVFtools?
=========================
Multisample Variant Format (MVF), is designed for compact storage and efficient analysis of multi-genome and multi-transcriptome datasets.  The programs provided in MVFtools support this format, both with conversion utilities, filtering and transformation programs, and data analysis and visualization modules.  MVF format is designed specifically for biological data analysis, since sequence data is encoded based on the information content at a particular aligned sequence site.  This contextual encoding allows for rapid computation of phylogenetic and population genetic analyses, and small file sizes that enable data sharing and distribution.


How do I cite this ?
===========================
Pease JB and BK Rosenzweig. 2016. "Encoding Data Using Biological Principles: the Multisample Variant Format for Phylogenomics and Population Genomics" *IEEE/ACM Transactions on Computational Biology and Bioinformatics*. In press. http://www.dx.doi.org/10.1109/tcbb.2015.2509997

Please also include the URL <https://www.github.com/jbpease/mvftools> in your methods section where the program is referenced.

Installation
============
No installation is required, mvftools scripts should work as long as Python3 is installed.  The repository can be cloned or downloaded as a .zip file from GitHub.

::
  git clone https://www.github.com/jbpease/mvftools

Alternatively, you can download MVftools as a .zip file from the github page.

Requirements
------------
* Python 3.x (2.7 should also work, but 3.x recommended) https://www.python.org/downloads/
* RAxML 8.x (7.x should also work, but 8.x recommended) https://sco.h-its.org/exelixis/web/software/raxml/index.html

Additional Requirements for Some Modules:
------------------------------------
  *  Scipy: (http://www.scipy.org/)
  * Biopython 1.6+: (http://www.biopython.org/),
  * Numpy (http://www.numpy.org/), 
  * RAxML (http://sco.h-its.org/exelixis/web/software/raxml/index.html/)

Preparing your data
===================

Sequence Alignment
------------------

MVF files can be created from VCF, FASTA, and MAF files using the ``vcf2mvf.py``, ``fasta2mvf.py``, or ``maf2mvf.py`` programs respectively.  Once converted to MVF format, analyses and manipulations can be carried out using the rest of the tools in MVFtools.


Basic usage examples
====================

**Case #1: Generate phylogenies from 100kb windows using a VCF data**::

  python3 vcf2mvf.py --vcf DATA.vcf --mvf DATA.mvf
  python3 mvf_window_tree.py --mvf DATA.mvf --out WINDOWTREES.txt --windowsize 100000

**Case #2: Convert a large FASTA file, then generate window-based counts for DFOIL/D-statistic introgression testing from the first five samples**::

  python3 fasta2mvf.py --fasta DATA.fasta --mvf DATA.mvf
  python3 mvf_analyze_dna.py PatternCount --mvf DATA.mvf --out PATTERNS.txt --windowsize 100000 --samples 0 1 2 3 4 

The file is now ready to use as an input file for with dfoil (http://www.github.com/jbpease/dfoil).

