#!/powerapps/share/centos7/Python-3.6.7/bin/python
# -*- coding: utf-8 -*-
"""
Created on Sun Oct 22 10:16:41 2017

@author: Oren
"""

import os
import argparse
from subprocess import call
import logging


def generate_qsub_file(queue_name, tmp_dir, cmd, prefix_name, qsub_path, cpus, nodes):
    '''compose qsub_file content and fetches it'''
    qsub_file_content = '#!/bin/bash -x\n'  # 'old bash: #!/bin/tcsh -x\n'
    qsub_file_content += '#PBS -S /bin/bash\n'  # '#PBS -S /bin/tcsh\n'
    qsub_file_content +=f'#PBS -l select={nodes}:ncpus={cpus}:mpiprocs=1:ompthreads={cpus}\n' # f'PBS -l nodes={nodes}:ppn={cpus}\n'
    qsub_file_content += f'#PBS -q {queue_name}\n'
    qsub_file_content += f'#PBS -N {prefix_name}\n'
    qsub_file_content += f'#PBS -e {tmp_dir}\n'  # error log
    qsub_file_content += f'#PBS -o {tmp_dir}\n'  # output log
    qsub_file_content += f'hostname\n'
    qsub_file_content += f'echo job_name: {prefix_name}\n'
    qsub_file_content += f'echo $PBS_JOBID\n'
    qsub_file_content += f'module list\n'
    qsub_file_content += f'{cmd}\n'
    with open(qsub_path, 'w') as f_qsub:  # write the job
        f_qsub.write(qsub_file_content)
    call(['chmod', '+x', qsub_path])  # set execution permissions

    logging.debug('First job details for debugging:')
    logging.debug('#' * 80)
    logging.debug('-> qsub_path is:\n' + qsub_path)
    logging.debug('\n-> qsub_file_content is:\n' + qsub_file_content)
    logging.debug('-> out file is at:\n' + os.path.join(tmp_dir, prefix_name + '.$JOB_ID.out'))
    logging.debug('#' * 80)


def submit_cmds_from_file_to_q(cmds_file, tmp_dir, queue_name, cpus, nodes,dummy_delimiter, start,
                               end, additional_params):
    logging.debug('-> Jobs will be submitted to ' + queue_name + '\'s queue')
    logging.debug('-> out, err and pbs files will be written to:\n' + tmp_dir + '/')
    logging.debug('-> Jobs are based on cmds ' + str(start) + ' to ' + str(end) + ' (excluding) from:\n' + cmds_file)
    logging.debug('-> Each job will use ' + cpus + ' CPU(s)\n')

    logging.debug('Starting to send jobs...')
    cmd_number = 0
    with open(cmds_file) as f_cmds:
        for line in f_cmds:
            if int(start) <= cmd_number < end and not line.isspace():
                try:
                    cmd, prefix_name = line.rstrip().split('\t')
                except:
                    logging.error(f'UNABLE TO PARSE LINE:\n{line}')
                    raise
                    # the queue does not like very long commands so I use a dummy delimiter (!@# by default) to break the rows:
                cmd = cmd.replace(dummy_delimiter, '\n')
                qsub_path = os.path.join(tmp_dir, prefix_name + '.pbs')  # path to job

                generate_qsub_file(queue_name, tmp_dir, cmd, prefix_name, qsub_path, cpus,nodes)

                # execute the job
                # queue_name may contain more arguments, thus the string of the cmd is generated and raw cmd is called
                terminal_cmd = f'/opt/pbs/bin/qsub {qsub_path} {additional_params}'
                logging.info(f'Submitting: {terminal_cmd}')

                call(terminal_cmd, shell=True)

            cmd_number += 1

    logging.debug('@ -> Sending jobs is done. @')


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('cmds_file',
                        help='A file containing jobs commands to execute in the queue. Each row should contain a (set of) command(s separated by $dummy_delimiter) then a "\t" and a job name',
                        type=lambda file_path: str(file_path) if os.path.exists(file_path) else parser.error(
                            f'{file_path} does not exist!'))
    parser.add_argument('tmp_dir', help='A temporary directory where the log files will be written to')
    parser.add_argument('-q', '--queue_name', help='The cluster to which the job(s) will be submitted to',
                        default='pupkolab')  # , choices=['pupko', 'itaym', 'lilach', 'bioseq'])
    parser.add_argument('--cpu', help='How many CPUs will be used?', choices=[str(i) for i in range(1, 29)],
                        default='1')
    parser.add_argument('--nodes', help='How many nodes will be used?',
                        default='1')
    parser.add_argument('--dummy_delimiter',
                        help='The queue does not "like" very long commands; A dummy delimiter is used to break each row into different commands of a single job',
                        default='!@#')
    parser.add_argument('--start', help='Skip jobs until $start', type=int, default=0)
    parser.add_argument('--end', help='Skip jobs from $end+1', type=int, default=float('inf'))
    parser.add_argument('-v', '--verbose', help='Increase output verbosity', action='store_true')
    parser.add_argument('--additional_params', help='Other specific parameters, such as, which machine to use',
                        default='')

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    logging.debug(f'args = {args}')

    if not os.path.exists(args.tmp_dir):
        logging.debug(f'{args.tmp_dir} does not exist. Creating tmp path...')
        os.makedirs(args.tmp_dir, exist_ok=True)

    submit_cmds_from_file_to_q(args.cmds_file, args.tmp_dir, args.queue_name, args.cpu, args.nodes
                               , args.dummy_delimiter,
                               args.start, args.end, args.additional_params)
