#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This program makes phylogenies from individual genomic windows of
a DNA MVF alignment (Requires: BioPython).
"""

import os
import sys
import argparse
import subprocess
from random import randint
from datetime import datetime
from io import StringIO
from itertools import combinations
from Bio import Phylo
from mvfbase import MultiVariantFile
from mvfbiolib import MvfBioLib
MLIB = MvfBioLib()


_LICENSE = """
MVFtools: Multisample Variant Format Toolkit
James B. Pease and Ben K. Rosenzweig
http://www.github.org/jbpease/mvftools

If you use this software please cite:
Pease JB and BK Rosenzweig. 2016.
"Encoding Data Using Biological Principles: the Multisample Variant Format
for Phylogenomics and Population Genomics"
IEEE/ACM Transactions on Computational Biology and Bioinformatics. In press.
http://www.dx.doi.org/10.1109/tcbb.2015.2509997

This file is part of MVFtools.

MVFtools is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
MVFtools is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with MVFtools.  If not, see <http://www.gnu.org/licenses/>.
"""


class WindowData(object):
    """Container for window data
        Arguments:
            labels: sequence labels
            hapsplt: split mode (none, randomone, randomboth, majorminor)
            seqs: list of sequence strings
    """
    def __init__(self, window_params=None, seqs=None):
        self.contigname = window_params.get('contigname', 'CONTIG')
        self.windowstart = window_params.get('windowstart', -1)
        self.windowsize = window_params.get('windowsize', -1)
        self.labels = window_params.get('labels', '')
        self.seqs = [[] for _ in range(len(self.labels))]

    def append_alleles(self, alleles, mindepth=1):
        """Add alleles to the window
            Arguments:
                alleles: list of allele strings
        """
        site_depth = mindepth + 0
        i = 0
        while site_depth and i < len(alleles):
            if alleles[i] in 'AaTtGgCcUu':
                site_depth -= 1
            i += 1
        if not site_depth:
            for j, allele in enumerate(alleles):
                try:
                    self.seqs[j].append(allele)
                except:
                    raise RuntimeError(alleles, len(self.seqs), len(alleles))
        return ''

    def prepare_alignment(self, params):
        """Checks and prepares alignment for RAxML
            Arguments:
                params: dict job parameters

            Returns list of any duplicates and empty entry when all checks pass
            In the case of errors, returns entry with information
        """
        # CHECK OVERALL ALIGNMENT DEPTH
        if len(self.seqs) < params.get('mindepth', 4):
            return ('', {'status': 'few',
                         'contig': self.contigname,
                         'windowstart': self.windowstart,
                         'windowsize': self.windowsize,
                         'alignlength': (
                             len(self.seqs[0]) if len(self.seqs) > 0 else 0),
                         'aligndepth': len(self.seqs) or 0})
        # CHECK FOR OVERALL ALIGNMENT LENGTH
        if len(self.seqs[0]) < params.get('minsites', 0):
            return ('', {'status': 'short',
                         'contig': self.contigname,
                         'windowstart': self.windowstart,
                         'windowsize': self.windowsize,
                         'alignlength': len(self.seqs[0]),
                         'aligndepth': len(self.seqs)})
        # CHECK FOR EMPTY SEQUENCES
        self.remove_empty_sequences()
        if not self.seqs:
            return ('', {'status': 'few.proc',
                         'contig': self.contigname,
                         'windowstart': self.windowstart,
                         'windowsize': self.windowsize,
                         'alignlength': (self.seqs and
                                         len(self.seqs[0]) or 0),
                         'aligndepth': len(self.seqs) or 0})
        # CHECK FOR EMPTY SITES
        self.remove_empty_sites()
        if not self.seqs[0]:
            return ('', {'status': 'short.proc',
                         'contig': self.contigname,
                         'windowstart': self.windowstart,
                         'windowsize': self.windowsize,
                         'alignlength': (self.seqs and
                                         len(self.seqs[0]) or 0),
                         'aligndepth': len(self.seqs) or 0})
        # CHECK FOR MINIMUM SEQUENCE COVERAGE
        if params.get('minseqcoverage', 0):
            self.remove_low_coverage_sequences(
                mincov=params.get('minseqcoverage', 0))
            if not self.seqs:
                return ('', {'status': 'spotty.proc',
                             'contig': self.contigname,
                             'windowstart': self.windowstart,
                             'windowsize': self.windowsize,
                             'alignlength': (self.seqs and
                                             len(self.seqs[0]) or 0),
                             'aligndepth': len(self.seqs) or 0})
        # CHECK AGAIN FOR EMPTY SITES
        self.remove_empty_sites()
        if len(self.seqs[0]) < params.get('dminsites', 0):
            return ('', {'status': 'short.proc',
                         'contig': self.contigname,
                         'windowstart': self.windowstart,
                         'windowsize': self.windowsize,
                         'alignlength': len(self.seqs[0]),
                         'aligndepth': len(self.seqs)})
        # CHECK FOR IDENTICAL DUPLICATE SEQUENCES BY BASE COMPOSITION
        duplicates = ''
        if params.get('duplicateseq', 'dontuse') in ('dontuse', 'remove'):
            duplicates = self.remove_duplicates(params.get('duplicateseq',
                                                           'dontuse'))
        # CHECK AGAIN FOR OVERALL ALIGNMENT DEPTH
        if len(self.seqs) < params.get('few.dup', 4):
            return ('', {'status': 'mindepth',
                         'contig': self.contigname,
                         'windowstart': self.windowstart,
                         'windowsize': self.windowsize,
                         'alignlength': (
                             len(self.seqs[0]) if len(self.seqs) > 0 else 0),
                         'aligndepth': len(self.seqs) or 0})

        # IF ALL OTHER CHECKS PASS, RETURN DUPLICATE LIST AND EMPTY ENTRY
        return (duplicates, {})

    def maketree_raxml(self, params):
        """Runs RAXML, and processes output
            Arguments:
                params: dict job parameters
        """
        # Prepare alignment and check for problems
        (duplicates, entry) = self.prepare_alignment(params)
        if entry:
            return entry
        # Alignment Has Passed Preliminary Checks, ready for RAxML run
        # Establish Temporary Directory
        jobname = "{}.{}-{}".format(
            params.get("tempprefix", "mvftree"),
            datetime.now().strftime('%Y-%m-%d-%H-%M-%S'),
            randint(100000, 999999))
        temp_filepath = os.path.abspath(
            "{}/{}_temp.phy".format(params['tempdir'], jobname))
        # Temporarily Shorten Labels for Use in Phylip
        temp_labels = {'encode': {}, 'decode': {}}
        for labellen in (len(x) > 10 for x in self.labels):
            if labellen:
                for j, oldlabel in enumerate(self.labels):
                    newlabel = 's{}'.format(j)
                    temp_labels['encode'][oldlabel] = newlabel
                    temp_labels['decode'][newlabel] = oldlabel
                    self.labels[j] = newlabel
                break
        params['outgroups'] = params.get('outgroups', False) and [
            temp_labels['encode'].get(x, x) for x in params['outgroups']] or []
        self.write_phylip(temp_filepath)
        try:
            run_raxml(temp_filepath, jobname, params)
            if params.get('bootstrap', 0):
                tree = Phylo.read('RAxML_bipartitions.' + jobname, 'newick',
                                  comments_are_confidence=True)
            else:
                tree = Phylo.read('RAxML_bestTree.' + jobname, 'newick')
        except IOError:
            return {'status': 'IOerror',
                    'contig': self.contigname,
                    'windowstart': self.windowstart,
                    'windowsize': self.windowsize,
                    'alignlength': len(self.seqs[0]),
                    'aligndepth': len(self.seqs)}
        if temp_labels['decode']:
            self.labels = [temp_labels.get(x, x) for x in self.labels]
        for node in tree.get_terminals():
            node.name = temp_labels['decode'].get(node.name, node.name)
            if node.name in duplicates:
                name_list = [node.name] + duplicates[node.name]
                node.split(n=len(duplicates[node.name]) + 1,
                           branch_length=0.00000)
                node.name = None
                for j, subnode in enumerate(node.get_terminals()):
                    subnode.name = name_list[j]
        tree.ladderize()
        full_tree = tree.__format__('newick').replace(
            ':1.00000;', ';').replace("'", '')
        for node in tree.find_clades():
            node.branch_length = None
            if not node.is_terminal:
                node.name = ''
        if params['rootwith']:
            params['rootwith'] = [x for x in params['rootwith']
                                  if x in self.labels]
        topology = ladderize_alpha_tree(
            tree.__format__('newick'),
            rootwith=params.get('rootwith', self.labels[0]),
            prune=params.get('prune', []))
        return {'status': 'ok',
                'duplicates': bool(duplicates),
                'contig': self.contigname,
                'windowstart': self.windowstart,
                'windowsize': self.windowsize,
                'tree': full_tree.strip(),
                'topology': topology.strip(),
                'alignlength': len(self.seqs[0]),
                'aligndepth': len(self.seqs)}

    def write_phylip(self, outpath):
        """Write Phylip"""
        with open(outpath, 'w') as alignfile:
            alignfile.write("{} {}\n".format(len(self.seqs),
                                             len(self.seqs[0])))
            for j in range(len(self.seqs)):
                alignfile.write("{} {}\n".format(self.labels[j],
                                                 ''.join(self.seqs[j])))
        return ''

    def remove_empty_sequences(self):
        """Remove sequences with no data"""
        removal_list = []
        for j in range(len(self.seqs)):
            if all([x in 'Xx-' for x in self.seqs[j]]):
                removal_list.append(j)
        for j in sorted(removal_list, reverse=True):
            del self.seqs[j]
            del self.labels[j]
        return ''

    def remove_low_coverage_sequences(self, mincov=0.):
        """Removes lowcoverage sequences"""
        removal_list = []
        if mincov:
            for i, seq in enumerate(self.seqs):
                cov = (float(sum([int(x in 'AaTtGgCcUu') for x in seq])) /
                       (float(len(seq))))
                if cov < mincov:
                    removal_list.append(i)
        for j in sorted(removal_list, reverse=True):
            del self.seqs[j]
            del self.labels[j]
        return ''

    def remove_empty_sites(self):
        """Remove sites without data"""
        removal_list = []
        for j in range(len(self.seqs[0])):
            isempty = True
            for base in (seq[j] for seq in self.seqs):
                if base in 'AaTtGgCcUu':
                    isempty = False
                    break
            if isempty:
                removal_list.append(j)
        if removal_list:
            self.seqs = [[base for (j, base) in enumerate(seq)
                          if j not in removal_list]
                         for seq in self.seqs]
        return ''

    def remove_duplicates(self, mode='dontuse'):
        """Remove duplicate sequences"""
        duplicates = {}
        remove_indices = set([])
        for i, j in combinations(range(len(self.seqs)), 2):
            duplicate = True
            for k, base in enumerate(self.seqs[i]):
                if base is not self.seqs[j][k]:
                    duplicate = False
                    break
            if duplicate:
                remove_indices.update([j])
                if mode is 'dontuse':
                    if self.labels[i] not in duplicates:
                        duplicates[self.labels[i]] = []

                    duplicates[self.labels[i]].append(self.labels[j])
        for j in sorted(remove_indices, reverse=True):
            del self.seqs[j]
            del self.labels[j]
        return duplicates


class OutputFile(object):
    """Set up Output File
        Params:
            path: file path
            headers: list of header elements
    """

    def __init__(self, path, headers):
        self.headers = headers
        self.path = os.path.abspath(path)
        self.write_headers()

    def write_headers(self):
        """Write headers to file"""
        with open(self.path, 'w') as outfile:
            outfile.write('#' + '\t'.join(self.headers) + "\n")
        return ''

    def write_entry(self, entry):
        """Writes entry to file
            Arguments:
                entry: dict of values with keys matching header
        """
        with open(self.path, 'a') as outfile:
            outfile.write("\t".join([str(entry.get(k, '.'))
                                     for k in self.headers]) + "\n")
        return ''


def verify_raxml(params):
    """verify raxml path"""
    out = str(subprocess.check_output([params['raxmlpath'], "-v"]))
    if out.find("RAxML version") == -1:
        raise RuntimeError("RAxML failed!\n{}".format(out))
    return ''


def run_raxml(filename, jobname, params):
    """Runs RAxML
        Parameters:
            filename: temporary phy filepath
            jobname: unique jobid for RAxML
            raxmlpath: path to RAxML program (default=raxmlHPC)
            outgroup: list of outgroup labels
            threads: multithreading tasks (experimental)
            bootstrap: int bootstrap replicates (default=none)
            optbranch: run -k option for RAxML
            opts: any additional options (as a string)
    """
    outgroups = params.get('outgroups', '') or []
    logpath = params.get('logpath', jobname + '.log')
    log_file = open(logpath, 'a')
    cmd = [params.get('raxmlpath', 'raxmlHPC'),
           '-m', params.get('model', 'GTRGAMMA'),
           '-n', jobname,
           '-s', filename,
           '-p', str(randint(1, 100000000))]
    if outgroups:
        cmd.extend(['-o', ','.join(outgroups)])
    if params.get('bootstrap', 0):
        if params.get('optbranch', 0):
            cmd.extend(['-k', '-#', str(params['bootstrap']),
                        '-f', 'a', '-x', str(randint(1, 100000000))])
        else:
            cmd.extend(['-#', str(params['bootstrap']), '-f', 'a', '-x',
                        str(randint(1, 100000000))])
    cmd.append(params.get('raxmlopts', ''))
    process = subprocess.Popen(' '.join(cmd), shell=True,
                               stdout=log_file, stderr=log_file)
    process.communicate()
    log_file.close()
    return ''


def ladderize_alpha_tree(treestring, prune=None, rootwith=None):
    """Ladderizes and Alphabetizes the Tree to create a unique
       string for each topology
    """
    tree0 = Phylo.read(StringIO(treestring), 'newick')
    for node in tree0.get_terminals():
        if prune:
            if any([x in node.name for x in prune]):
                tree0.prune(node)
    for node in tree0.find_clades():
        node.branch_length = 1.0
    for node in tree0.get_nonterminals(order="postorder"):
        if not sum([int(not x.is_terminal) for x in node.clades]):
            node.clades.sort(key=lambda c: sorted([
                x.name for x in c.get_terminals()])[0])
        else:
            node.clades.sort(key=lambda c: c.name)
    tree0.ladderize()
    if rootwith:
        for node in tree0.get_nonterminals():
            if all([subnode.name in rootwith for subnode
                    in node.get_terminals()]):
                tree0.root_with_outgroup(node)
                break
    tree_string = tree0.__format__('newick').replace(
        ':1.00000', '').rstrip()
    return tree_string


def hapsplit(alleles, mode):
    """Process Alleles into Haplotypes"""
    if all([x not in 'RYMKWS' for x in alleles]):
        return (alleles if mode in ['major', 'minor', 'randomone'] else
                ''.join([base*2 for base in alleles]))
    elif mode in ['major', 'minor', 'majorminor']:
        hapleles = ''.join([MLIB.hapsplit[x] for x in alleles])
        counts = sorted([(hapleles.count(x), x) for x in set(hapleles)],
                        reverse=True)
        order = [x[1] for x in counts]
        newalleles = []
        for base in alleles:
            if base in 'RYMKWS':
                newalleles.extend([
                    x for x in order if x in MLIB.hapsplit[base]])
            else:
                newalleles.extend([base, base])
        if mode is 'major':
            alleles = ''.join([x[0] for x in newalleles])
        elif mode is 'minor':
            alleles = ''.join([x[1] for x in newalleles])
        elif mode is 'majorminor':
            alleles = ''.join([x for x in newalleles])
    elif mode is 'randomone':
        alleles = ''.join([MLIB.hapsplit[x][randint(0, 1)] for x in alleles])
    elif mode is 'randomboth':
        randx = randint(0, 1)
        alleles = ''.join([
            MLIB.hapsplit[x][randx] + MLIB.hapsplit[x][1 - randx]
            for x in alleles])
    return alleles


def generate_argparser():
    parser = argparse.ArgumentParser(
        prog="mvf_windows_tree.py",
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog=_LICENSE)
    parser.add_argument("-i", "--mvf", required=True, type=os.path.abspath,
                        help="Input MVF file.")
    parser.add_argument("-o", "--out", required=True, type=os.path.abspath,
                        help="Tree list output text file.")
    parser.add_argument("-s", "--samples", nargs='*',
                        help="One or more taxon labels (default=all)")
    parser.add_argument("-g", "--raxml-outgroups", "--raxml_outgroups",
                        nargs="*",
                        help="Outgroups taxon labels to use in RAxML.")
    parser.add_argument("-r", "--rootwith", nargs='*',
                        help="Root output trees with these taxa after RAxML.")
    parser.add_argument("-c", "--contigs", nargs='*',
                        help="Contig ids to use in analysis (default=all)")
    parser.add_argument("--outputcontiglabels", action="store_true",
                        help=("Output will use contig labels instead of id "
                              "numbers."))
    parser.add_argument("-e", "--outputempty", action="store_true",
                        help=("Include entries of windows with no data in "
                              "output."))
    parser.add_argument("-A", "--choose_allele", "--hapmode",
                        default="none", dest="choose_allele",
                        choices=["none", "randomone", "randomboth",
                                 "major", "minor", "majorminor"],
                        help=("Chooses how heterozygous alleles are "
                              "handled. (none=no splitting (default); "
                              "randomone=pick one allele randomly "
                              "(recommended); randomboth=pick two alleles "
                              "randomly, but keep both; major=pick the "
                              "more common allele; minor=pick the less "
                              "common allele; majorminor= pick the major in "
                              "'a' and minor in 'b'"))
    parser.add_argument("-w", "--windowsize", type=int, default=10000,
                        help=("specify genomic region size, "
                              "or use -1 for whole contig"))
    parser.add_argument("-M", "--minsites", type=int, default=100,
                        help="minimum number of sites ")
    parser.add_argument("-C", "--minseqcoverage", type=float, default=0.1,
                        help="""proportion of total alignment a sequence
                                must cover to be retianed [0.1]""")
    parser.add_argument("-D", "--mindepth", type=int, default=4,
                        help=("minimum number of alleles per site"))
    parser.add_argument("-b", "--bootstrap", type=int,
                        help=("turn on rapid bootstrapping for RAxML and "
                              "perform specified number of replicates"))
    parser.add_argument("-m", "--raxml_model", default="GTRGAMMA",
                        help=("choose RAxML model"))
    parser.add_argument("-X", "--raxmlpath", default="raxml",
                        help="RAxML path for manual specification.")
    parser.add_argument("-R", "--raxmlopts", default="",
                        help=("specify additional RAxML arguments as a "
                              "double-quotes encased string"))
    parser.add_argument("-d", "--duplicateseq", default="dontuse",
                        choices=["dontuse", "keep", "remove"],
                        help=("dontuse=remove duplicate sequences prior to "
                              "RAxML tree inference, then add them to the "
                              "tree manually as zero-branch-length sister "
                              "taxa; keep=keep in for RAxML tree inference "
                              "(may cause errors for RAxML); "
                              "remove=remove entirely from alignment"))
    parser.add_argument("--tempdir", default='./raxmltemp',
                        type=os.path.abspath,
                        help=("Temporary directory path"))
    parser.add_argument("--tempprefix", default="mvftree",
                        help="Temporary file prefix")
    parser.add_argument("--quiet", action="store_true",
                        help="suppress screen output")
    parser.add_argument("--version", action="version",
                        version="2017-06-24",
                        help="display version information")
    return parser


def main(arguments=None):
    """Main method"""
    arguments = sys.argv[1:] if arguments is None else arguments
    parser = generate_argparser()
    args = parser.parse_args(args=arguments)
    # ESTABLISH FILE OBJECTS
    args.contigs = args.contigs or []
    mvf = MultiVariantFile(args.mvf, 'read')
    treefile = OutputFile(args.out,
                          headers=['contig', 'windowstart', 'windowsize',
                                   'tree', 'topology', 'topoid',
                                   # 'templabels', ### USED FOR DEBUGGING ###
                                   'alignlength', 'aligndepth', 'status'])
    topofile = OutputFile(args.out + '.counts',
                          headers=['rank', 'topology', 'count'])
    sample_cols = (None if args.samples is None else
                   mvf.get_sample_indices(args.samples))
    if not os.path.exists(args.tempdir):
        os.mkdir(args.tempdir)
    os.chdir(args.tempdir)
    # SETUP PARAMS
    main_labels = mvf.get_sample_labels(sample_cols)
    if args.choose_allele in ['randomboth', 'majorminor']:
        main_labels = [label + x for x in ['a', 'b'] for label in main_labels]
    params = {'outgroups': args.raxml_outgroups or [],
              'rootwith': args.rootwith or [],
              'minsites': args.minsites,
              'minseqcoverage': args.minseqcoverage,
              'mindepth': args.mindepth,
              'raxmlpath': args.raxmlpath,
              'raxmlopts': args.raxmlopts,
              'duplicateseq': args.duplicateseq,
              'model': args.raxml_model,
              'bootstrap': args.bootstrap,
              'windowsize': args.windowsize,
              'choose_allele': args.choose_allele,
              'tempdir': args.tempdir,
              'tempprefix': args.tempprefix}
    # WINDOW START INTERATION
    verify_raxml(params)
    current_contig = ''
    window_start = 0
    window = None
    topo_ids = {}
    topo_counts = {}
    for contig, pos, allelesets in mvf.iterentries(
            contigs=args.contigs, subset=sample_cols, quiet=args.quiet,
            no_invariant=False, no_ambig=False, no_gap=False, decode=True):
        if contig is not current_contig or (args.windowsize is not -1 and (
                pos > window_start + args.windowsize)):
            if window:
                entry = window.maketree_raxml(params)
                if entry['status'] is not 'ok':
                    if args.outputempty:
                        treefile.write_entry(entry)
                else:
                    topo = entry["topology"]
                    topo_counts[topo] = topo_counts.get(topo, 0) + 1
                    if topo not in topo_ids:
                        topo_ids[topo] = (topo_ids and
                                          max(topo_ids.values()) + 1 or 0)
                    entry["topoid"] = topo_ids[topo]
                    treefile.write_entry(entry)
                window_start = ((contig is current_contig and
                                 args.windowsize is not -1) and
                                window_start + args.windowsize or 0)
            current_contig = contig[:]
            window = None
            window = WindowData(window_params={
                'contigname': (args.outputcontiglabels and
                               mvf.get_contig_label(current_contig) or
                               current_contig[:]),
                "windowstart": ('-1' if args.windowsize == -1
                                else window_start + 0),
                "windowsize": args.windowsize,
                "labels": main_labels[:]})
        # ADD ALLELES
        if args.choose_allele is not 'none':
            allelesets[0] = hapsplit(allelesets[0], args.choose_allele)
        window.append_alleles(allelesets[0], mindepth=args.mindepth)
    # LAST LOOP
    if window:
        entry = window.maketree_raxml(params)
        if entry['status'] is not 'ok':
            if args.outputempty:
                treefile.write_entry(entry)
        else:
            topo = entry["topology"]
            topo_counts[topo] = topo_counts.get(topo, 0) + 1
            if topo not in topo_ids:
                topo_ids[topo] = (
                    max(topo_ids.values()) + 1 if topo_ids else 0)
            entry["topoid"] = topo_ids[topo]
            treefile.write_entry(entry)
        window = None
    # END WINDOW ITERATION
    topo_list = sorted([(v, k) for k, v in topo_counts.items()],
                       reverse=True)
    for rank, [value, topo] in enumerate(topo_list):
        topofile.write_entry({'rank': rank, 'count': value, 'topology': topo})
    return ''

if __name__ == "__main__":
    main()
