from training_and_test_set_generation import Lasso_training_and_test
from config import IGNORE_COLS_IN_CSV
from lasso_model_analysis import compare_lasso_to_naive_approaches_on_test_set, calculate_test_ll_using_sampled_data
from partitioned_analysis import get_mean_param_per_group
from help_functions import write_to_sampled_alignment_path, create_or_clean_dir
import matplotlib.pyplot  as plt
import pickle
import logging
from scipy.stats import chisquare
import os
import numpy as np


def get_lasso_configurations(curr_msa_version_folder, args, brlen_generators, curr_msa_stats, training_size_options):
    '''

    :param curr_msa_version_folder:
    :param args:
    :param brlen_generators:
    :param curr_msa_stats:
    :param training_size_options:
    :return: Wrapper for function Lasso_training_and_test that runs the Lasso model on each configuration.
    '''
    curr_msa_version_lasso_dump = os.path.join(curr_msa_version_folder, 'lasso.dump')
    curr_msa_version_lasso_dump_baseline = curr_msa_version_lasso_dump.replace(args.run_prefix,
                                                                               args.lasso_baseline_run_prefix)
    if os.path.exists(curr_msa_version_lasso_dump_baseline):
        with open(curr_msa_version_lasso_dump_baseline, 'rb') as handle:
            logging.info(
                "Using lasso dump files in {} ".format(curr_msa_version_lasso_dump))
            lasso_configurations_per_training_size = pickle.load(handle)
    else:
        lasso_configurations_per_training_size = Lasso_training_and_test(brlen_generators, curr_msa_stats,
                                                                         training_size_options,
                                                                         args.random_trees_test_size)
        with open(curr_msa_version_lasso_dump, 'wb') as handle:
            pickle.dump(lasso_configurations_per_training_size, handle, protocol=pickle.HIGHEST_PROTOCOL)
    return lasso_configurations_per_training_size


def high_rate_bias_test(curr_run_directory, curr_msa_stats, partitioned_rates, per_loci_partition, optimized_random_trees_path):
    '''

    :param curr_run_directory:
    :param curr_msa_stats:
    :param partitioned_rates:
    :param per_loci_partition:
    :param optimized_random_trees_path:
    :return: Take 3 most fast evolving genes and calculate log-likelihood on test data with respect to the obtained MSA
    '''
    highest_rate_genes = sorted(partitioned_rates, key=partitioned_rates.get, reverse=True)[:3]
    highest_rate_corresponding_locis = list((np.where(np.isin(np.array(per_loci_partition), highest_rate_genes)))[0])
    highest_rate_sampled_msa = os.path.join(curr_run_directory, "highest_rate_msa")
    write_to_sampled_alignment_path(curr_msa_stats["alignment_data"], highest_rate_sampled_msa,
                                    highest_rate_corresponding_locis,
                                    curr_msa_stats["file_type_biopython"])
    high_rate_bias_folder = os.path.join(curr_run_directory, "high_rate_comparison")
    create_or_clean_dir(high_rate_bias_folder)
    high_rate_results, high_rate_results_no_opt = calculate_test_ll_using_sampled_data(curr_msa_stats,
                                                                                       curr_run_directory,
                                                                                       highest_rate_sampled_msa,
                                                                                       weights_file_path=None,
                                                                                       lasso_intercept=0,
                                                                                       chosen_locis=highest_rate_corresponding_locis,
                                                                                       optimized_random_trees_path=optimized_random_trees_path,
                                                                                       prefix_opt="opt_high_rate",
                                                                                       prefix_eval="eval_high_rate")
    return high_rate_results


def loci_dist_partitioned_analysis(curr_msa_stats, threshold, lasso_evaluation_result, partitioned_rates):
    '''

    :param curr_msa_stats:
    :param threshold:
    :param lasso_evaluation_result:
    :param partitioned_rates:
    :return: Calculate expected and observed distribution of chosen positions across genes
    '''
    chosen_locis = curr_msa_stats["lasso_chosen_locis"]
    logging.info(f"Partition count = {curr_msa_stats['per_loci_partition']}")
    partitions_count_arr = np.bincount(curr_msa_stats["per_loci_partition"])
    partitioned_coeffs = get_mean_param_per_group(curr_msa_stats["lasso_chosen_weights"],
                                                  np.take(np.array(curr_msa_stats['per_loci_partition']),
                                                          curr_msa_stats["lasso_chosen_locis"]))
    expected_chosen_locis_count_arr = (np.bincount(curr_msa_stats["per_loci_partition"]) * threshold).astype(int)
    chosen_locis_partitions_count_arr = np.bincount(curr_msa_stats["per_loci_partition"][chosen_locis])
    chosen_locis_partitions_count_arr = np.pad(chosen_locis_partitions_count_arr,
                                               (0, len(partitions_count_arr) - len(chosen_locis_partitions_count_arr)),
                                               mode='constant')
    obs_vs_expected = np.divide(chosen_locis_partitions_count_arr, partitions_count_arr)
    rates = [partitioned_rates.get(i) for i in range(len(obs_vs_expected))]
    coeffs = [partitioned_coeffs.get(i) for i in range(len(obs_vs_expected))]
    try:
        chi_square_statistics = chisquare(chosen_locis_partitions_count_arr, f_exp=expected_chosen_locis_count_arr)

    except:
        chi_square_statistics = -1
    lasso_evaluation_result["expected_partition_counts"] = expected_chosen_locis_count_arr
    lasso_evaluation_result["partition_mean_rates"] = rates
    lasso_evaluation_result["partition_mean_coeff"] = coeffs
    lasso_evaluation_result["full_data_counts"] = partitions_count_arr
    lasso_evaluation_result["observed_partition_counts"] = chosen_locis_partitions_count_arr
    lasso_evaluation_result["chi_square_partition"] = chi_square_statistics


def perform_only_lasso_pipeline(training_size_options, brlen_generators, curr_msa_stats,
                                lasso_configurations_per_training_size,
                                job_csv_path, all_msa_results, curr_run_directory):
    '''

    :param training_size_options:
    :param brlen_generators:
    :param curr_msa_stats:
    :param lasso_configurations_per_training_size:
    :param job_csv_path:
    :param all_msa_results:
    :param curr_run_directory:
    :return: Use Lasso results to generate a results csv
    '''
    for brlen_generator_name in brlen_generators:
        curr_msa_stats["brlen_generator"] = brlen_generator_name
        for training_size in training_size_options:
            curr_msa_stats["actual_training_size"] = training_size
            lasso_results = lasso_configurations_per_training_size[brlen_generator_name][training_size]
            for threshold in lasso_results:
                curr_msa_stats["actual_sample_pct"] = threshold
                curr_msa_stats.update(lasso_results[threshold])
                logging.info(
                    "only evaluating lasso on brlen {} and training size {}: ".format(brlen_generator_name,
                                                                                      training_size))
                lasso_evaluation_result = {k: curr_msa_stats[k] for k in curr_msa_stats.keys() if
                                           k not in IGNORE_COLS_IN_CSV
                                           }
                if curr_msa_stats["compare_lasso_to_naive"]:
                    lasso_comparisons_results = compare_lasso_to_naive_approaches_on_test_set(curr_msa_stats,
                                                                                              curr_run_directory,
                                                                                              threshold)
                    lasso_evaluation_result.update(lasso_comparisons_results)
                if curr_msa_stats["compare_loci_gene_distribution"] and curr_msa_stats[
                    'per_loci_partition'] is not None:
                    partitioned_rates = get_mean_param_per_group(curr_msa_stats["rate4site_scores"],
                                                                 curr_msa_stats['per_loci_partition'])
                    loci_dist_partitioned_analysis(curr_msa_stats, threshold, lasso_evaluation_result,
                                                   partitioned_rates)
                    test_dump_path = os.path.join(curr_run_directory, f"Lasso_folder/test_{curr_msa_stats['random_trees_test_size']}_random_trees_eval/test_set.dump")
                    if not os.path.exists(test_dump_path):
                        test_dump_path = test_dump_path.replace(curr_msa_stats["run_prefix"],
                                                                curr_msa_stats["training_set_baseline_run_prefix"])

                        test_data = pickle.load(open(test_dump_path, "rb"))
                    else:
                        test_data = curr_msa_stats
                    optimized_random_trees_path = test_data.get("optimized_test_topologies_path",
                                                                test_data.get("test_optimized_trees_path"))
                    true_ll_values = test_data["test_ll_values"]
                    high_gene_test_results = high_rate_bias_test(curr_run_directory, curr_msa_stats, partitioned_rates,
                                                                 curr_msa_stats['per_loci_partition'], optimized_random_trees_path)
                    lasso_test_results = calculate_test_ll_using_sampled_data(curr_msa_stats, curr_run_directory,
                                                                              weights_file_path=curr_msa_stats[
                                                                                  "weights_file_path"],
                                                                              sampled_alignment_path=
                                                                              curr_msa_stats[
                                                                                  "sampled_alignment_path"],
                                                                              lasso_intercept=curr_msa_stats[
                                                                                  "lasso_intercept"],
                                                                              chosen_locis=curr_msa_stats[
                                                                                  "lasso_chosen_locis"],
                                                                              prefix_opt="opt_lasso",
                                                                              prefix_eval="eval_lasso", optimized_random_trees_path = optimized_random_trees_path)
                    lasso_evaluation_result["lasso_test_approx"] = lasso_test_results
                    lasso_evaluation_result["fast_genes_approx"] = high_gene_test_results
                    lasso_evaluation_result["true_ll_values"] = true_ll_values

                all_msa_results = all_msa_results.append(lasso_evaluation_result, ignore_index=True)
                all_msa_results.to_csv(job_csv_path, index=False, sep='\t')
    return all_msa_results
