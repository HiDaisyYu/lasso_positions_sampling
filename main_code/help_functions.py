import os
import pandas as pd
import shutil
from Bio import SeqIO
from Bio.SeqRecord import SeqRecord
from Bio.Seq import Seq
from config import SEED,CSV_MSAs_FOLDER,MODULE_LOAD_STR
import logging
import subprocess
import sys
import numpy as np
import random


def generate_argument_list(args):
    output = []
    for arg in vars(args):
        if not type(getattr(args, arg)) == bool:
            value = ["--" + arg, str(getattr(args, arg))]
        elif (getattr(args, arg)) == True:
            value = ["--" + arg]
        else:
            value = []
        output = output + value
    print(output)
    return output


def generate_argument_str(args):
    output = ""
    for arg in vars(args):
        if not type(getattr(args, arg)) == bool:
            value = "--" + arg + " " + str(getattr(args, arg))
        elif (getattr(args, arg)) == True:
            value = "--" + arg
        else:
            value = ""
        output = output + value + " "
    return output.strip()


def submit_linux_job(job_name, job_folder, run_command, cpus, job_ind="job", queue='pupkolab'):
    create_dir_if_not_exists(job_folder)
    cmds_path = os.path.join(job_folder, str(job_ind) + ".cmds")
    job_log_path = os.path.join(job_folder, str(job_ind) + "_tmp_log")
    job_line = f'{MODULE_LOAD_STR} {run_command}\t{job_name}'
    logging.debug("About to run on {} queue: {}".format(queue, job_line))
    with open(cmds_path, 'w') as cmds_f:
        cmds_f.write(job_line)
    command = f'/groups/pupko/edodotan/q_submitter_power.py {cmds_path} {job_log_path} --cpu {cpus} -q {queue}'
    logging.debug(f'About to submit a pbs file to {queue} queue based on cmds:{cmds_path}')
    os.system(command)


def update_dict_with_a_suffix(dest_dict, input_dict, suffix):
    for orig_key in input_dict:
        new_key = str(orig_key)+str(suffix)
        dest_dict[new_key] = input_dict[orig_key]



def submit_local_job(executable, argument_list):
    theproc = subprocess.Popen([sys.executable, executable] + argument_list)
    theproc.communicate()


def remove_MSAs_with_not_enough_seq_and_locis(file_path_list, min_seq, min_n_loci):
    proper_file_path_list = []
    for path in file_path_list:
        file_type_biopython = extract_file_type(path, True)
        with open(path) as file:
            data = list(SeqIO.parse(file, file_type_biopython))
            n_seq = len(data)
            n_loci = len(data[0])
            if n_seq >= min_seq and n_loci>= min_n_loci:
                proper_file_path_list.append(path)
    return proper_file_path_list


def write_to_sampled_alignment_path(original_alignment_data, sampled_alignment_path, samp_indexes, file_type):
    sampled_sequence = []
    for original_record in original_alignment_data:
        sampled_seq = Seq(''.join([str(original_record.seq[ind]) for ind in samp_indexes]))
        sampled_record = SeqRecord(sampled_seq, id=original_record.id, name=original_record.name,
                                   description=original_record.description)
        sampled_sequence.append(sampled_record)
    val = SeqIO.write(sampled_sequence, sampled_alignment_path, file_type)
    if not val == len(original_alignment_data):
        logging.error("   #ERROR: Sampled columns not written succesfully to file " + sampled_alignment_path)


def remove_gaps_and_trim_locis(sample_records, max_n_loci, loci_shift, per_loci_partition_results):
    all_data = np.array([list(record.seq) for record in sample_records])
    count_gaps_per_column = np.count_nonzero(((all_data == "-") | (all_data == "X")), axis=0)
    non_gapped_data = all_data[:, count_gaps_per_column < all_data.shape[0]]
    if per_loci_partition_results is not None:
        corrected_partitioned_results = per_loci_partition_results[count_gaps_per_column < all_data.shape[0]][loci_shift:loci_shift + max_n_loci]
    else:
        corrected_partitioned_results = None
    loci_trimmed_data = non_gapped_data[:, loci_shift:loci_shift + max_n_loci]
    new_sampled_records = []
    for i, old_record in enumerate(sample_records):
        sampled_record = SeqRecord(Seq("".join(list(loci_trimmed_data[i, :]))), id=old_record.id, name=old_record.name,
                                   description=old_record.description)
        new_sampled_records.append(sampled_record)
    return new_sampled_records, corrected_partitioned_results


def trim_n_seq(original_seq_records, number_of_sequences, seed):
    seq_trimmed_seq_records = []
    seq_values = set()
    random.seed(seed)
    random.shuffle(original_seq_records)
    for record in original_seq_records:
        if len(seq_trimmed_seq_records) >= number_of_sequences:
            break
        if str(record.seq) in seq_values:
            continue
        else:
            sampled_record = SeqRecord(record.seq, id=record.id, name=record.name,
                                       description=record.description)
            seq_values.add(str(record.seq))
            seq_trimmed_seq_records.append(sampled_record)
    return seq_trimmed_seq_records


def count_unique_n_seq(original_seq_records):
    seq_values = set()
    for record in original_seq_records:
        seq = np.array(list(record.seq))
        undetermined_deq = seq[(seq == "-") | (seq == "X")]
        if len(undetermined_deq) < len(seq):
            seq_values.add("".join(seq))
    return len(seq_values)


def trim_MSA(original_alignment_data, trimmed_alignment_path, number_of_sequences, file_type, max_n_loci, loci_shift,partition_results):
    obtained_n_seq = -1
    i = 0
    while obtained_n_seq < number_of_sequences and i <= 100:
        seq_trimmed_seq_records = trim_n_seq(original_alignment_data, number_of_sequences, seed=SEED + i)
        loci_trimmed_seq_records, corrected_partitioned_results = remove_gaps_and_trim_locis(seq_trimmed_seq_records, max_n_loci, loci_shift,partition_results)
        obtained_n_seq = count_unique_n_seq(loci_trimmed_seq_records)
        i = i + 1
    logging.info("obtained {obtained_n_seq} sequences after {i} iterations!".format(obtained_n_seq=obtained_n_seq, i=i))
    try:
        SeqIO.write(loci_trimmed_seq_records, trimmed_alignment_path, file_type)
        logging.info(" {} sequences written succesfully to new file {}".format(len(seq_trimmed_seq_records),
                                                                               trimmed_alignment_path))
    except:
        logging.error("ERROR! {} sequences NOT written succesfully to new file {}".format(number_of_sequences,
                                                                                          trimmed_alignment_path))
    return corrected_partitioned_results

def extract_file_type(path, change_format=False, ete=False):
    filename, file_extension = os.path.splitext(path)
    if change_format:
        if file_extension == '.phy':
            file_extension = 'iphylip' if ete == True else 'phylip-relaxed'
        elif file_extension == ".fasta":
            file_extension = 'fasta'
        elif file_extension == ".nex":
            file_extension = 'nexus'
    return file_extension


def delete_file_content(file_path):
    with open(file_path, 'w'):
        pass


def extract_alignment_files_from_dir(path):
    if os.path.isfile(path):
        return [path]
    files_list = []
    if os.path.exists(path):
        for file in os.listdir(path):
            if file.endswith(".phy") or file.endswith(".fasta"):  # or file.endswith(".nex")
                files_list.append(os.path.join(path, file))
    return files_list


def extract_dir_list_from_csv(dir_list_csv_path):
    df = pd.read_csv(dir_list_csv_path)
    df.sort_values(by='nchars', ascending=False, inplace=True)
    dir_list = [os.path.join(CSV_MSAs_FOLDER, path) for path in list(df["path"])]
    logging.debug("Number of paths in original csv = {n_paths}".format(n_paths=len(df.index)))
    return dir_list


def extract_alignment_files_from_general_csv(dir_list_csv_path):
    files_list = []
    logging.debug("Extracting alignments from {}".format(dir_list_csv_path))
    dir_list = extract_dir_list_from_csv(dir_list_csv_path)
    for dir in dir_list:
        if os.path.exists(dir):
            for file in os.listdir(dir):
                if (file.endswith(".phy") or file.endswith(".fasta")):
                    files_list.append(os.path.join(dir, file))
                    break
        else:
            logging.error("Following MSA dir does not exist {dir}".format(dir=dir))
    logging.debug("Overalls number of MSAs found in the given directories is: {nMSAs}".format(nMSAs=len(files_list)))
    return files_list


def alignment_list_to_df(alignment_data):
    alignment_list = [list(alignment_data[i].seq) for i in range(len(alignment_data))]
    loci_num = len(alignment_data[0].seq)
    columns = list(range(0, loci_num))
    original_alignment_df = pd.DataFrame(alignment_list, columns=columns)
    return original_alignment_df


def delete_dir_content(dir_path):
    for filename in os.listdir(dir_path):
        file_path = os.path.join(dir_path, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)

        except Exception as e:
            logging.error('Failed to delete %s. Reason: %s' % (file_path, e))
            return False
    return True


def create_or_clean_dir(dir):
    if os.path.exists(dir):
        delete_dir_content(dir)
    else:
        os.mkdir(dir)


def create_dir_if_not_exists(dir):
    if not os.path.exists(dir):
        os.mkdir(dir)


def unify_text_files(input_path_list, output_file_path, str_given=False):
    with open(output_file_path, 'w') as outfile:
        if str_given:
            for input in input_path_list:
                outfile.write(input)
        else:
            for fname in input_path_list:
                with open(fname) as infile:
                    outfile.write(infile.read())
    return output_file_path


def add_csvs_content(csvs_path_list, unified_csv_path):
    existing_df = [pd.read_csv(unified_csv_path,sep ='\t')] if os.path.exists(unified_csv_path) else []
    existing_df_size = pd.read_csv(unified_csv_path,sep ='\t').size if os.path.exists(unified_csv_path) else 0
    logging.info('Existing df size is: {}'.format(existing_df_size))
    non_empty_df = [pd.read_csv(f,sep ='\t') for f in csvs_path_list if not pd.read_csv(f,sep ='\t').empty]
    combined_df = pd.concat(non_empty_df + existing_df, sort=False)
    combined_df_size = combined_df.size
    logging.info('Combined df size is: {}'.format(combined_df_size))
    combined_df.to_csv(unified_csv_path, index=False, sep ='\t')
    return combined_df

def remove_empty_columns(csv_path):
    if os.path.exists((csv_path)):
        df = pd.read_csv(csv_path,sep ='\t')
        df = df.dropna(how='all', axis=1)
        df.to_csv(csv_path, index=False, sep ='\t')





def get_job_related_files_paths(curr_job_folder, job_ind):
    job_status_file = os.path.join(curr_job_folder, str(job_ind) + "_status")
    job_csv_path = os.path.join(curr_job_folder, str(job_ind) + ".csv")
    job_msa_paths_file = os.path.join(curr_job_folder, "file_paths_" + str(job_ind))
    general_log_path = os.path.join(curr_job_folder, "job_" + str(job_ind) + "_general_log.log")
    return {"job_status_file": job_status_file, "job_csv_path": job_csv_path, "job_msa_paths_file": job_msa_paths_file,
            "general_log_path": general_log_path}



def get_positions_stats(alignment_df):
    alignment_df_fixed = alignment_df.replace('-', np.nan)
    gap_positions_pct = np.mean(alignment_df_fixed.isnull().sum() / len(alignment_df_fixed))
    counts_per_position = [dict(alignment_df_fixed[col].value_counts(dropna=True)) for col in list(alignment_df)]
    probabilities = [list(map(lambda x: x / sum(counts_per_position[col].values()), counts_per_position[col].values()))
                     for col in
                     list(alignment_df)]
    entropy = [sum(list(map(lambda x: -x * np.log(x), probabilities[col]))) for col in list(alignment_df)]
    avg_entropy = np.mean(entropy)
    constant_sites_pct = sum([1 for et in entropy if et == 0]) / len(entropy)
    return constant_sites_pct, avg_entropy, gap_positions_pct
