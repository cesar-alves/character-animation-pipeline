# Unit test run

Command: `python3 -m unittest discover -s tests -v`

```text
test_fit_hash_recorded (test_build_record.BuildRecordTests.test_fit_hash_recorded) ... ok
test_record_round_trip (test_build_record.BuildRecordTests.test_record_round_trip) ... ok
test_scan_vendor_hashes (test_build_record.BuildRecordTests.test_scan_vendor_hashes) ... ok
test_duplicate_names_rejected (test_job.JobTests.test_duplicate_names_rejected) ... ok
test_missing_clip_file_detected (test_job.JobTests.test_missing_clip_file_detected) ... ok
test_resolve_character_returns_absolute_paths (test_job.JobTests.test_resolve_character_returns_absolute_paths) ... ok
test_unknown_fields_and_bad_schema_rejected (test_job.JobTests.test_unknown_fields_and_bad_schema_rejected) ... ok
test_valid_jobs_load_and_normalize (test_job.JobTests.test_valid_jobs_load_and_normalize) ... ok
test_write_tmp_job_contract (test_job.JobTests.test_write_tmp_job_contract) ... ok
test_bad_date_rejected (test_mirror.MirrorTests.test_bad_date_rejected) ... ok
test_copy_to_godot_writes_expected_path (test_mirror.MirrorTests.test_copy_to_godot_writes_expected_path) ... ok
test_custom_subdir (test_mirror.MirrorTests.test_custom_subdir) ... ok
test_mirror_writes_manifest_and_checksums (test_mirror.MirrorTests.test_mirror_writes_manifest_and_checksums) ... ok
test_nonempty_dated_folder_refuses_without_force (test_mirror.MirrorTests.test_nonempty_dated_folder_refuses_without_force) ... ok
test_require_drive_without_root_raises (test_mirror.MirrorTests.test_require_drive_without_root_raises) ... ok
test_skip_without_drive_root (test_mirror.MirrorTests.test_skip_without_drive_root) ... ok
test_camera_in_file_fails (test_validate.ValidateTests.test_camera_in_file_fails) ... ok
test_light_extension_fails (test_validate.ValidateTests.test_light_extension_fails) ... ok
test_malformed_glb_returns_error_report (test_validate.ValidateTests.test_malformed_glb_returns_error_report) ... ok
test_missing_clip_fails (test_validate.ValidateTests.test_missing_clip_fails) ... ok
test_missing_skin_fails (test_validate.ValidateTests.test_missing_skin_fails) ... ok
test_profile_bone_match (test_validate.ValidateTests.test_profile_bone_match) ... ok
test_root_translation_must_be_constant (test_validate.ValidateTests.test_root_translation_must_be_constant) ... ok
test_valid_fixture_passes (test_validate.ValidateTests.test_valid_fixture_passes) ... ok
test_write_report_uses_two_space_indent (test_validate.ValidateTests.test_write_report_uses_two_space_indent) ... ok

----------------------------------------------------------------------
Ran 25 tests in 0.011s

OK
```
