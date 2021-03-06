#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This program checks an MVF file for inconsistencies or errors
"""

import os
import sys
import argparse
from mvfbase import MultiVariantFile

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


class MvfTransformer(object):
    """MVF Transformer Object
       Creates a Data Structure to translate sample and contig names
       across mulitple MVF files
       Arguments:
           labels: dict of sample labels
           contigs: dict of contig info

    """

    def __init__(self, labels=None, contigs=None):
        self.contigs = contigs or {}
        self.labels = labels or {}

    def set_label(self, localindex, consensusindex):
        """Set label transform
        """
        self.labels[consensusindex] = localindex
        return ''

    def set_contig(self, localid, consensusid):
        """Set contigid transform
        """
        self.contigs[consensusid] = localid
        return ''


def generate_argparser():
    parser = argparse.ArgumentParser(
        prog="mvf_join.py",
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog=_LICENSE)
    parser.add_argument("-i", "--mvf", nargs="*", type=os.path.abspath,
                        help="One or more mvf files.",
                        required=True)
    parser.add_argument("-o" "--out", help="Output mvf file.",
                        required=True, type=os.path.abspath)
    parser.add_argument("-c", "--newcontigs", action="store_true",
                        help=("By default, contigs are matched between files "
                              "using their text labels in the header. "
                              "Use this option to turn matching off and treat "
                              "each file's contigs as distinct."))
    parser.add_argument("-s", "--newsamples", action="store_true",
                        help=("By default, samples are matched between files "
                              "using their text labels in the header. "
                              "Use this option to turn matching off and treat "
                              "each file's sample columns as distinct."))
    parser.add_argument("-B", "--linebuffer", type=int, default=100000,
                        help="number of entries to write in a block")
    parser.add_argument("-M", "--main_header_file",
                        help=("Output file will use same headers as "
                              "this input file (default=first in list)."))
    parser.add_argument("--overwrite", action="store_true",
                        help="USE WITH CAUTION: force overwrite of outputs")
    parser.add_argument("--quiet", action="store_true",
                        help="suppress progress meter")
    parser.add_argument("--version", action="version",
                        version="2017-06-24",
                        help="display version information")
    return parser


def main(arguments=None):
    """Main method"""
    arguments = sys.argv[1:] if arguments is None else arguments
    parser = generate_argparser()
    args = parser.parse_args(args=arguments)
    concatmvf = MultiVariantFile(args.out, 'write', overwrite=args.overwrite)
    # Copy the first file's metadata
    if args.main_header_file:
        if args.main_header_file not in args.mvf:
            raise RuntimeError("{} not found in files".format(
                args.main_header_file))
        else:
            args.main_header_file = args.mvf.index(args.main_header_file)
    else:
        args.main_header_file = 0
    first_mvf = MultiVariantFile(args.mvf[args.main_header_file], 'read')
    concatmvf.metadata = first_mvf.metadata.copy()
    # Open each MVF file, read headers to make unified header
    transformers = []
    for mvfname in args.mvf:
        # This will create a dictionary of samples{old:new}, contigs{old:new}
        transformer = MvfTransformer()
        mvf = MultiVariantFile(mvfname, 'read')
        for i, label in enumerate(mvf.get_sample_labels()):
            if label not in concatmvf.get_sample_labels():
                concatmvf.metadata['labels'].append(label)
                concatmvf.metadata['samples'][
                    concatmvf.metadata['labels'].index(label)] = {
                        'label': label}
            if concatmvf.metadata['labels'].index(label) != i:
                transformer.set_label(
                    i, concatmvf.metadata['labels'].index(label))
        for contigid, contigdata in iter(mvf.metadata['contigs'].items()):
            if contigdata['label'] not in [
                    concatmvf.metadata['contigs'][x]['label']
                    for x in concatmvf.metadata['contigs']]:
                newid = (contigid not in concatmvf.metadata['contigs'] and
                         contigid or concatmvf.get_next_contig_id())
                concatmvf.metadata['contigs'][newid] = contigdata
            else:
                for concatid, concatdata in (
                        concatmvf.metadata['contigs'].items()):
                    if contigdata['label'] == concatdata['label']:
                        newid = concatid
                        break
            if newid != contigid:
                transformer.set_contig(contigid, newid)
        transformers.append(transformer)
    # Write output header
    concatmvf.write_data(concatmvf.get_header())
    # Now loop through each file
    entries = []
    nentries = 0
    for ifile, mvfname in enumerate(args.mvf):
        if not args.quiet:
            sys.stderr.write("Processing {} ...\n".format(mvfname))
        transformer = transformers[ifile]
        mvf = MultiVariantFile(mvfname, 'read')
        for contigid, pos, allelesets in mvf.iterentries(decode=False,
                                                         quiet=args.quiet):
            if transformer.labels:
                allelesets = [mvf.decode(x) for x in allelesets]
                for j, alleles in enumerate(allelesets):
                    allelesets[j] = concatmvf.encode(''.join([
                        x in transformer.labels and
                        alleles[transformer.labels[x]] or alleles[x]
                        for x in range(len(alleles))]))
            if transformer.contigs:
                contigid = (contigid in transformer['contigs'] and
                            transformer['contigs'][contigid] or
                            contigid)
            entries.append((contigid, pos, allelesets))
            nentries += 1
            if nentries == args.linebuffer:
                concatmvf.write_entries(entries)
                entries = []
                nentries = 0
        if entries:
            concatmvf.write_entries(entries)
            entries = []
            nentries = 0
        if not args.quiet:
            sys.stderr.write("done\n")
    return ''


if __name__ == "__main__":
    main()
