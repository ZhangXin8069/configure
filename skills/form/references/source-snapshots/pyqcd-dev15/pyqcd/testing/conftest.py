"""PyQCD 集成测试入口：``python -m pyqcd.testing`` 或 pytest。"""

from pyqcd.testing import (  # noqa: F401
    test_gamma_basis,
    test_gevp_preserves_complex_hermitian_data,
    test_zr_parametrization,
    test_gradient_flow_su3_and_dissipation,
    test_wilson_flow_is_gauge_covariant,
    test_wilson_flow_zero_time_is_identity,
    test_wilson_flow_hits_requested_time,
    test_wilson_flow_rejects_invalid_time_controls,
    test_gauge_observables_contracts,
    test_flow_action_density_is_gauge_invariant_and_nonnegative,
    test_flow_action_density_weak_field_normalization,
    test_gradient_flow_gluon_reference_contracts,
    test_tmd_operator_runs,
    test_tmd_staple_matches_explicit_three_segment_path,
    test_tmd_staple_is_gauge_covariant,
    test_tmd_matrix_element_is_gauge_invariant,
    test_tmd_operator_uses_tx_ty_xy_lorentz_pairs,
    test_tmd_batch_reuses_clover_fields_and_staples,
    test_tmd_empty_batch_skips_geometry_work,
    test_matching_kernel,
    test_hybrid_ratio,
    test_tmd_extraction_chain,
    test_tmd_soft_factor_ze_contracts,
    test_sftx_flow_time_units_contracts,
    test_scale_setting_flow_behavior,
    test_hyp_smear,
    test_hyp_smear_is_gauge_covariant,
    test_hyp_zero_outer_weight_returns_input,
    test_hyp_reduces_to_ape_when_inner_weights_zero,
    test_hyp_is_hypercubic_under_axis_relabeling,
    test_gradient_flow_tau_limit,
    test_ratio_fit_extraction,
    test_gpu_backend_consistency,
    test_torch_backend_consistency,
    test_end_to_end_synthetic_meff,
    test_matching_sum_rule,
    test_core_chain_integrated,
    test_tmd_matching_nlo,
    # 整合功能测试（~auto-all）
    test_stout_smear,
    test_stout_smear_is_gauge_covariant,
    test_stout_torch_cuda_device_contract,
    test_eigvec_compress,
    test_eigcompress_dtype_contracts,
    test_inner_product_returns_cross_gram_matrix,
    test_omega_uses_extract_count_per_input_block,
    test_omega_dim2_single_sampled_block_weights,
    test_omega_dim3_single_sampled_block_weights,
    test_omega_rejects_invalid_partition_contract,
    test_omega_n1_dim3_matches_hand_inclusion_probabilities,
    test_omega_normal_uses_symmetric_row_sum_balancing,
    test_omega_exact0_multiblock_dim2_hand_weights,
    test_omega_exact0_multiblock_dim3_hand_weights,
    test_cg_coefficients,
    test_hB_dataset_loader,
    test_zr_dataset_object_api,
    test_zr_dataset_object_reuses_prepared_inputs,
    test_hybrid_boot_covariance,
    test_tmd_plateau_and_cs_kernel,
    test_plot_tmd_pdf,
    test_pipeline_baryon_2pt_uses_trace_projection,
    test_pipeline_baryon_3pt_traces_spin_and_preserves_current,
    test_pipeline_pjnnjnp_4pt_traces_spin_and_preserves_current,
    test_pipeline_pion_projection_controls_are_unchanged,
    test_pipeline_projection_rejects_uncontracted_spin_shapes,
    test_pipeline_2pt_only_swallows_known_forbidden_neutron_channel,
    test_pjn_3pt_explicit_wick_oracle,
    test_staple_operator_public_contracts,
    test_tmd_su3_geometry_contracts,
    test_step_tmd_single_flow_contract,
    test_tmd_hybrid_renormalization_contracts,
    test_quasi_tmd_fourier_contracts,
    test_matching_grid_contracts,
    test_pipeline_persistence_contracts,
    test_pipeline_runtime_failure_contracts,
    test_correlated_fit_identifiability_guards,
    test_bootstrap_resampling_contracts,
    test_field_strength_cache_contracts,
    test_ope_channel_contracts,
    test_continuum_extrapolation_identifiability_contracts,
    test_fh_adaptive_window_contracts,
    test_vertex_product_binary_contracts,
    test_momentum_smearing_contracts,
    test_pipeline_validate_and_2pt_resume,
    test_pipeline_tmd_uses_dimensionless_flow_time,
    test_parallel_mpi_default_run_dir_is_broadcast,
    test_parallel_plan_does_not_report_unknown_memory_as_zero,
    test_mpi_run_directory_contracts,
    test_parallel_mpi_planning_contracts,
    test_parallel_mpi_reliability_contracts,
    test_parallel_mpi_collective_failure_contracts,
    test_proton_energy_dirs,
    test_dispersion_identifiability_contracts,
    test_round2_integrations,
    # 第三轮整合测试（~auto-all 第三遍清查 20260822）
    test_matching_ratio_kernels,
    test_quasi_pdf_gluon_sin_transform,
    test_gluon_ope_directions_and_ff,
    test_parity_boundary_projection,
    test_zr_sample_refit_loop,
    test_extrapolate_boot_fit,
    test_group_aggregate_and_disconnect,
    test_check_files_existence_guard,
    test_wickplot_and_flop_analysis,
    test_vertex_product_readers,
    test_env_snapshot,
    test_cmp_primitives,
    test_read_gauge_lime_accepts_contents_directory,
)


def main():
    """Run every test registered by the central testing package."""
    import traceback
    import unittest

    passed = skipped = failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
                passed += 1
            except unittest.SkipTest as exc:
                print(f"SKIP {name}: {exc}")
                skipped += 1
            except Exception:
                print(f"FAIL {name}")
                traceback.print_exc()
                failed += 1
    print(f"\n{passed} passed, {skipped} skipped, {failed} failed")
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
