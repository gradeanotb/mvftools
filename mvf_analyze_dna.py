#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MVFtools: Multisample Variant Format Toolkit
http://www.github.org/jbpease/mvftools

MVF_analyze_dna: Base analysis class handler and functions
@author: James B. Pease
@author: Ben K. Rosenzweig

version: 2015-06-11 - v.1.2.1 release
version: 2015-09-04 - upgrades and fixes
version: 2015-12-16 - change QuintetCount to general PatternCount
@version: 2016-03-18 - bug fixes

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

from __future__ import print_function
import sys
import argparse
from random import randint
from itertools import combinations
from mvfanalysisbase import AnalysisModule, OutputFile, abpattern
from mvfbase import MultiVariantFile
from mvfbiolib import HAPSPLIT
from time import time


MODULENAMES = ("BaseCountWindow", "Coverage", "DstatComb",
               "PairwiseDistance", "PatternCount")


class Coverage(AnalysisModule):
    """Calculate coverage stats for each sample column
    """

    def analyze(self, mvf):
        """Analyze Entries for Coverage Module
        """

        labels = mvf.get_sample_labels()
        for contig, _, allelesets in mvf.iterentries(
                contigs=self.params['contigs'], subset=self.params['samples'],
                decode=True):
            if contig not in self.data:
                self.data[contig] = dict.fromkeys(labels, 0)
                self.data[contig]['contig'] = contig
            for j, base in enumerate(allelesets[0]):
                self.data[contig][labels[j]] += int(
                    base not in 'Xx-')
            self.labels = labels
        self.write()
        return ''

    def write(self):
        """Write Output
        """
        outfile = OutputFile(path=self.params['out'],
                             headers=(["contig"] + self.labels))
        for contig in self.data:
            outfile.write_entry(self.data[contig])
        return ''


class PositionDepth(AnalysisModule):
    """Calculate sample coverage stats across all positions
    """

    def analyze(self, mvf):
        """Analyze Entries for PositionDepth module"""
        for contig, pos, allelesets in mvf:
            if contig not in self.data:
                self.data[contig] = dict.fromkeys(self.params['labels'], 0)
                self.data[contig]['contig'] = contig
            for j, base in enumerate(allelesets[0]):
                self.data[contig][self.params['labels'][j]] += int(
                    base not in 'Xx-')
        self.write()
        return ''

    def write(self):
        """Write Output
        """
        outfile = OutputFile(path=self.params['out'],
                             headers=(["contig"] + self.params['labels']))
        for contig in self.data:
            outfile.write_entry(self.data[contig])
        return ''


class DstatComb(AnalysisModule):
    """Calculate genome-wide D-statstics for
       all possible trio combinations of samples
    """

    def analyze(self, mvf):
        self.params['nsamples'] = len(self.params['samples']) - 1
        self.params['samplenames'] = [
            mvf.metadata['samples'][x]['label']
            for x in mvf.metadata['samples']]
        self.params['contigs'] = set([])
        for contig, _, allelesets in mvf:
            self.params['contigs'].update([contig])
            alleles = mvf.decode(allelesets[0])
            if alleles[-1] in 'XN-':
                continue
            for i in range(self.params['nsamples'] - 2):
                if alleles[i] not in 'ATGC':
                    continue
                for j in range(i + 1, self.params['nsamples'] - 1):
                    if alleles[j] not in 'ATGC':
                        continue
                    for k in range(j + 1, self.params['nsamples']):
                        if alleles[k] not in 'ATGC':
                            continue
                        subset = [alleles[x] for x in [i, j, k, -1]]
                        if subset[-1] not in subset[:3]:
                            continue
                        if len(set(subset)) != 2:
                            continue
                        val = (1 * (subset[j] == subset[-1]) +
                               2 * (subset[k] == subset[-1]))
                        trio = (i, j, k)
                        if trio not in self.data:
                            self.data[trio] = {}
                        if contig not in self.data[trio]:
                            self.data[trio][contig] = [0, 0, 0]
                        print(val)
                        self.data[trio][contig][val - 1] += 1
        self.write()

    def write(self):
        """Writes output
        """
        headers = ['sample0', 'sample1', 'sample2']
        for contig in self.params['contigs']:
            headers.extend(['{}:abba'.format(contig), '{}:baba'.format(contig),
                            '{}:bbaa'.format(contig), '{}:D'.format(contig)
                            ])
        outfile = OutputFile(path=self.params['out'], headers=headers)
        for i, j, k in combinations(range(self.params['nsamples']), 3):
            trio = tuple([i, j, k])
            if trio not in self.data:
                continue
            entry = dict([('sample{}'.format(i),
                          self.params['samplenames'][x][0])
                          for i, x in enumerate(trio)])
            for contig in self.params['contigs']:
                if contig not in self.data[trio]:
                    entry.update(dict().fromkeys([
                        '{}:abba'.format(contig), '{}:baba'.format(contig),
                        '{}:bbaa'.format(contig), '{}:D'.format(contig)],
                        '0'))
                else:
                    [abba, baba, bbaa] = self.data[trio][contig]
                    if abba > baba and abba > bbaa:

                        dstat = zerodiv(baba - bbaa, baba + bbaa)
                    elif baba > bbaa and baba > abba:
                        dstat = zerodiv(abba - bbaa, abba + bbaa)
                    else:
                        dstat = zerodiv(abba - baba, abba + baba)
                    entry.update([('{}:abba'.format(contig), abba),
                                  ('{}:baba'.format(contig), baba),
                                  ('{}:bbaa'.format(contig), bbaa),
                                  ('{}:D'.format(contig), dstat)
                                  ])
            outfile.write_entry(entry)
        return ''


class PatternCount(AnalysisModule):
    """Count biallelic patterns spatially along
       chromosomes (e.g,, for use in DFOIL or Dstats
       http://www.github.com/jbpease/dfoil)
    """

    def analyze(self, mvf):
        """Analyze Entries for PatternCount Module
        """
        labels = mvf.get_sample_labels()
        self.params['labels'] = labels[:]
        current_contig = None
        current_position = 0
        sitepatterns = {}
        samples = [labels.index(x) for x in self.params['samples']]
        self.params['nsamples'] = len(samples)
        for contig, pos, allelesets in mvf:
            if not current_contig:
                current_contig = contig[:]
            if contig != current_contig or (
                    pos > current_position + self.params['windowsize']):
                self.data[(current_contig, current_position)] = dict([
                    ('contig', current_contig),
                    ('position', current_position)] +
                     sitepatterns.items())
                sitepatterns = {}
                if contig != current_contig:
                    current_position = 0
                    current_contig = contig[:]
                else:
                    current_position += self.params['windowsize']
            if len(allelesets[0]) == 1:
                if allelesets[0] in 'ATGC':
                    pattern = 'A' * self.params['nsamples']
                else:
                    continue
            elif allelesets[0][1] == '+':
                continue
            else:
                alleles = mvf.decode(allelesets[0])
                alleles = [alleles[x] for x in samples]
                if any(x in alleles for x in 'X-RYKMWS'):
                    continue
                if len(set(alleles)) > 2:
                    continue
                pattern = ''.join([x == alleles[-1] and 'A' or 'B'
                                   for x in alleles[:-1]]) + 'A'
            sitepatterns[pattern] = sitepatterns.get(pattern, 0) + 1
        if sitepatterns:
            self.data[(current_contig, current_position)] = dict([
                ('contig', current_contig),
                ('position', current_position)] +
                 sitepatterns.items())

        self.write()
        return ''

    def write(self):
        """Write Output
        """
        headers = ['contig', 'position']
        headers.extend(
            [abpattern(x, self.params['nsamples'])
             for x in range(0, 2 ** self.params['nsamples'], 2)])
        outfile = OutputFile(path=self.params['out'],
                             headers=headers)
        sorted_entries = sorted([(self.data[k]['contig'],
                                  self.data[k]['position'], k)
                                 for k in self.data])
        for _, _, k in sorted_entries:
            outfile.write_entry(self.data[k])
        return ''


class BaseCountWindow(AnalysisModule):
    """Count the number of and relative rate of certain bases
       spatially along chromosomes
    """

    def analyze(self, mvf):
        """Analyze Entries for GroupUniqueAlleleWindow Module"""
        labels = mvf.get_sample_labels()
        self.params['labels'] = labels[:]
        current_contig = None
        current_position = 0
        match_counts = dict().fromkeys(labels, 0)
        total_counts = dict().fromkeys(labels, 0)
        all_match = 0
        all_total = 0
        for contig, pos, allelesets in mvf:
            if self.params.get('mincoverage'):
                if (sum([int(x not in 'Xx-') for x in allelesets[0]]) <
                        self.params['mincount']):
                    continue

            if not current_contig:
                current_contig = contig[:]
            if contig != current_contig or (
                    pos > current_position + self.params['windowsize']):
                self.data[(current_contig, current_position)] = {
                    'contig': current_contig, 'position': current_position}
                for k in match_counts:
                    self.data[(current_contig, current_position)].update([
                        (k + '.match', match_counts[k] + all_match),
                        (k + '.total', total_counts[k] + all_total),
                        (k + '.prop', (total_counts[k] + all_total and
                                       (float(match_counts[k] + all_match) /
                                        float(total_counts[k] + all_total)) or
                                       0))])
                if contig != current_contig:
                    current_contig = contig[:]
                    current_position = 0
                else:
                    current_position += self.params['windowsize']
                match_counts = dict().fromkeys(labels, 0)
                total_counts = dict().fromkeys(labels, 0)
                all_total = 0
                all_match = 0
            else:
                alleles = allelesets[0]
                if len(alleles) == 1:
                    if alleles in self.params['basematch']:
                        all_match += 1
                    if alleles in self.params['basetotal']:
                        all_total += 1
                else:
                    alleles = mvf.decode(alleles)
                    for i, base in enumerate(alleles):
                        if base in self.params['basematch']:
                            match_counts[labels[i]] += 1
                        if base in self.params['basetotal']:
                            total_counts[labels[i]] += 1
        self.write()
        return ''

    def write(self):
        """Write Output"""
        headers = ['contig', 'position']
        for label in self.params['labels']:
            headers.extend([label + x for x in ('.match', '.total', '.prop')])
        outfile = OutputFile(path=self.params['out'],
                             headers=headers)
        sorted_entries = sorted([(self.data[k]['contig'],
                                  self.data[k]['position'], k)
                                 for k in self.data])
        for _, _, k in sorted_entries:
            outfile.write_entry(self.data[k])
        return ''


class PairwiseDistance(AnalysisModule):
    """Calculated pairwise distances among samples"""

    def pairwise_distance(self, basepairs):
        total = 0
        diff = 0
        print(basepairs)
        for pairbases, paircount in iter(basepairs.items()):
            base0, base1 = pairbases[0], pairbases[1]
            if base0 not in 'ATGCKMRYWS' or base1 not in 'ATGCKMRYWS':
                print("ERROR", base0, base1)
                continue
            total += paircount
            if base0 in 'KMRYWS':
                base0 = HAPSPLIT[base0][randint(0, 1)]
            if base1 in 'KMRYWS':
                base1 = HAPSPLIT[base1][randint(0, 1)]
            if base0 != base1:
                diff += paircount
        print(diff, total)
        return diff, total

    def analyze(self, mvf):
        """Analyze for PairwiseDistance module"""
        self.params['labels'] = mvf.get_sample_labels()[:]
        ncol = mvf.metadata['ncol']
        base_matches = dict([(tuple(x), {})
                            for x in combinations(range(ncol), 2)])
        all_match = {}
        for _, _, allelesets in mvf:
            alleles = allelesets[0]
            if len(alleles) == 1:
                all_match[alleles + alleles] = (
                    all_match.get(alleles + alleles, 0) + 1)
                continue
            if alleles[1] == '+':
                if 'X' in alleles or '-' in alleles:
                    continue
                samplepair = (0, int(alleles[3:]))
                basepair = alleles[0] + alleles[2]
                base_matches[samplepair][basepair] = (
                    base_matches[samplepair].get(basepair, 0) + 1)
                continue
            alleles = mvf.decode(alleles)
            valid_positions = [i for i, x in enumerate(alleles)
                               if x not in 'X-']
            for i, j in combinations(valid_positions, 2):
                samplepair = (i, j)
                basepair = alleles[i] + alleles[j]
                base_matches[samplepair][basepair] = (
                    base_matches[samplepair].get(basepair, 0) + 1)
        all_diff, all_total = self.pairwise_distance(all_match)
        for samplepair in base_matches:
            ndiff, ntotal = self.pairwise_distance(base_matches[samplepair])
            self.data[samplepair] = {
                'taxa': "{};{}".format(self.params['labels'][samplepair[0]],
                                       self.params['labels'][samplepair[1]]),
                'ndiff': ndiff + all_diff,
                'ntotal': ntotal + all_total,
                'dist': zerodiv(ndiff + all_diff, ntotal + all_total)}

        self.write()
        return ''

    def write(self):
        """Write Output"""
        headers = ['taxa', 'ndiff', 'ntotal', 'dist']
        outfile = OutputFile(path=self.params['out'],
                             headers=headers)
        for _, entry in iter(self.data.items()):
            outfile.write_entry(entry)
        return ''


def zerodiv(a, b):
    if b == 0:
        return 0
    return float(a) / float(b)


def modulehelp(modulenames=MODULENAMES):
    """Prints extra description of modules"""
    for modulename in modulenames:
        print("{}: {}".format(modulename, eval(modulename + ".__doc__")))
    return ''


def main(arguments=sys.argv[1:]):
    """Main MVF Analysis"""
    parser = argparse.ArgumentParser(description="""
        A set of analysis modules to analyze MVFs of dna flavor
        options whose help text includes a [modulename]
        are module-specific and have no function in other modules.""")
    parser.add_argument("module", choices=MODULENAMES)
    parser.add_argument("--mvf", help="input MVF file")
    parser.add_argument("--out", help="output file")
    parser.add_argument("--contigs", nargs='*',
                        help="limit analyses to these contigs")
    parser.add_argument("--samples", nargs='*',
                        help="limit analyses to these samples")
    parser.add_argument("--mincoverage", type=int,
                        help="mininum sample coverage for site")
    parser.add_argument("--windowsize", type=int, default=100000,
                        help="""window size""")
    parser.add_argument("--basematch", help=(
        "[BaseCountWindow] string of bases to match (i.e. numerator)."))
    parser.add_argument("--basetotal", help=(
        "[BaseCountWindow] string of bases for total (i.e. denominator)"))
    parser.add_argument("--morehelp", action="store_true",
                        help="get additional information on modules")
    parser.add_argument("--version", action="store_true",
                        help="display version")
    args = parser.parse_args(args=arguments)
    if args.version:
        print("Version: 2016-03-18")
        sys.exit()
    time0 = time()
    # HELP MENU
    if args.morehelp:
        modulehelp(MODULENAMES)
        sys.exit()
    # ESTABLISH MVF
    mvf = MultiVariantFile(args.mvf, 'read')
    # MODULES
    if args.module == 'BaseCountWindow':
        module = BaseCountWindow(params=vars(args))
    elif args.module == 'Coverage':
        module = Coverage(params=vars(args))
    elif args.module == 'DstatComb':
        module = DstatComb(params=vars(args))
    elif args.module == 'PairwiseDistance':
        module = PairwiseDistance(params=vars(args))
    elif args.module == "PatternCount":
        module = PatternCount(params=vars(args))
    # RUN MODULE
    module.analyze(mvf)
    print("Finished in {} seconds.".format(time() - time0))
    return ''

if __name__ == "__main__":
    if "--morehelp" in sys.argv:
        modulehelp()
        sys.exit()
    main()
