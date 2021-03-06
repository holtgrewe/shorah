#!/usr/bin/env python

# Copyright 2007-2012
# Niko Beerenwinkel,
# Nicholas Eriksson,
# Moritz Gerstung,
# Lukas Geyrhofer,
# Kerensa McElroy,
# Osvaldo Zagordi,
# ETH Zurich

# This file is part of ShoRAH.
# ShoRAH is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# ShoRAH is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with ShoRAH.  If not, see <http://www.gnu.org/licenses/>.
''' shorah.py is the program that performs the global reconstruction.
    It runs error correction, global reconstruction and frequency estimation
    by calling the relevant programs. Additionally, it performs SNV discovery
    by calling the program snv.py
'''
import os
import os.path
import sys

import logging
import logging.handlers

# Make a global logging object.
sholog = logging.getLogger("ShorahLog")
# set logging level
sholog.setLevel(logging.DEBUG)
# This handler writes everything to a file.
LOG_FILENAME = './shorah.log'
h = logging.handlers.RotatingFileHandler(LOG_FILENAME, 'w',
                                         maxBytes=100000, backupCount=5)
f = logging.Formatter("%(levelname)s %(asctime)s %(funcName)s\
                      %(lineno)d %(message)s")
h.setFormatter(f)
sholog.addHandler(h)

dn = os.path.dirname(__file__)


def run_child(exe_name, arg_string):
    '''use subrocess to run an external program with arguments'''
    import subprocess

    if not arg_string.startswith(' '):
        arg_string = ' ' + arg_string

    try:
        retcode = subprocess.call(exe_name + arg_string, shell=True)
        if retcode < 0:
            sholog.error(exe_name + arg_string)
            sholog.error("Child %s terminated by signal" % exe_name, -retcode)
        else:
            sholog.debug("Child %s returned %i" % (exe_name, retcode))
    except OSError, ee:
        sholog.error("Execution of %s failed:" % exe_name, ee)

    return retcode


if __name__ == "__main__":

    import optparse
    import shutil
    import glob
    import dec
    import mm
    import snv
    import amplian

    # parse command line
    optparser = optparse.OptionParser()

    optparser.add_option("-b", "--bam", default="", type="string", dest="b",
                         help="sorted bam format alignment file")

    optparser.add_option("-f", "--fasta", default="", type="string", dest="f",
                         help="reference genome in fasta format")

    optparser.add_option("-a", "--alpha", default=0.1, type="float", dest="a",
                         help="alpha in dpm sampling <%default>")

    optparser.add_option("-w", "--windowsize", default=201, type="int",
                         dest="w", help="window size <%default>")

    # window shiftings, such that each base is covered up to win_shifts times
    optparser.add_option("-s", "--winshifts", default=3, type="int", dest="s",
                         help="number of window shifts <%default>",)

    optparser.add_option("-i", "--sigma", default=0.01, type="float", dest="i",
                         help="value of sigma to use when calling\
                         SNVs <%default>")

    optparser.add_option("-x", "--maxcov", default=10000, type="int", dest="x",
                         help="approximate max coverage allowed <%default>")

    optparser.add_option("-r", "--region", default='', type="string", dest="r",
                         help="region in format 'chr:start-stop',\
                         eg 'ch3:1000-3000'")

    optparser.add_option("-k", "--keep_files", default=False,
                         action="store_true", dest="k",
                         help="keep intermediate files <%default>")

    optparser.add_option("-p", "--amplicon", default=False,
                         action="store_true", dest="p",
                         help="run in amplicon mode <%default>")

    (options, args) = optparser.parse_args()
    del(args)
    sholog.info(' '.join(sys.argv))

    in_stem = '.'.join(os.path.split(options.b)[1].split('.')[:-1])

    if options.p:
        # amplicon_mode, run only diri_sampler and snv.py
        amplian.main(in_bam=options.b, in_fasta=options.f,
                     max_coverage=options.x, alpha=options.a)
    if not os.path.exists('snv/SNV.txt'):
        # 1. run dec.py
        sholog.debug('running dec.py')
        dec.main(in_bam=options.b, in_fasta=options.f, win_length=options.w,
                 win_shifts=options.s, max_coverage=options.x,
                 region=options.r, keep_files=options.k, alpha=options.a)

        # 2. copy file and run fas2read to convert from fasta
        shutil.move('%s.cor.fas' % in_stem, '%s_cor.fas' % in_stem)
        sholog.debug('running fas2reads')
        my_prog = 'perl -I %s %s' % (dn + '/perllib',
                                     os.path.join(dn, 'fas2read.pl'))
        my_arg = " -f %s_cor.fas" % in_stem
        assert os.path.isfile("%s_cor.fas" % in_stem), \
            'File %s_cor.fas not found' % in_stem
        retcode_f2r = run_child(my_prog, my_arg)
        if retcode_f2r:
            sholog.error('fas2read did not return 0')
            sys.exit('Something went wrong in fas2read')
        else:
            sholog.debug('fas2read exited successfully')

        # 3. run contain to eliminate redundant reads
        # output: filein.rest
        sholog.debug('running contain')
        my_prog = os.path.join(dn, 'contain')
        my_arg = " -f %s_cor" % in_stem
        assert os.path.isfile('%s_cor.fas' % in_stem), \
            'File %s_cor.fas not found' % in_stem
        retcode_c = run_child(my_prog, my_arg)
        if retcode_c:
            sholog.error('contain did not return 0')
            sys.exit('Something went wrong while running contain')
        else:
            sholog.debug('contain exited successfully')

        # 4. run mm.py to find minimal matching
        sholog.debug('running mm.py')
        mm.main('%s_cor.rest' % in_stem, maxhaplo=200)

        # 5. run EM freqEst output: sample.$nr.popl
        sholog.debug('running freqEst')
        my_prog = os.path.join(dn, 'freqEst')
        my_arg = " -f %s_cor" % in_stem
        assert os.path.isfile('%s_cor.rest' % in_stem), \
            'File %s_cor.rest not found' % in_stem
        retcode_em = run_child(my_prog, my_arg)
        if retcode_em:
            sholog.error('freqEst did not return 0')
            sys.exit('Something went wrong in the EM step')
        else:
            sholog.debug('freqEst exited successfully')

    # 6. run snv.py to parse single nucleotide variants
    sholog.debug('running snv.py')
    snv.main(reference=options.f, bam_file=options.b, sigma=options.i,
             increment=options.w / options.s)

    # tidy snvs
    try:
        os.mkdir('snv')
    except OSError:
        pass
    for snv_file in glob.glob('./SNV*'):
        shutil.move(snv_file, 'snv/')
