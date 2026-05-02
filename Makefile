# Library-Playground — claude.ai port build helpers
#
# `make skills`       — build dist/skills/<name>.zip for each skill
# `make clean-skills` — remove dist/ and build/
#
# Each skill zip bundles its SKILL.md plus the three helper modules
# from webhelper/ (librarian_query.py, sqlite_export.py,
# encoded_codec.py).  Skills are filesystem-based on the claude.ai
# sandbox VM, so the model invokes them as `python3 scripts/...`
# without any network fetch.

SKILLS := librarian-triage \
          librarian-quickref \
          librarian-build-setup \
          librarian-build-batches \
          librarian-build-finish \
          library-cataloguer

SKILL_DIR  := .claude.ai/skills
DIST_DIR   := dist/skills
BUILD_DIR  := build/skills
HELPER_DIR := webhelper

HELPERS := librarian_query.py sqlite_export.py encoded_codec.py
HELPER_SRCS := $(addprefix $(HELPER_DIR)/, $(HELPERS))

ZIPS := $(addprefix $(DIST_DIR)/, $(addsuffix .zip, $(SKILLS)))

.PHONY: skills clean-skills

skills: $(ZIPS)

# Real-file pattern target.  Make tracks dist/skills/<name>.zip and
# rebuilds when SKILL.md or any helper source changes.
$(DIST_DIR)/%.zip: $(SKILL_DIR)/%/SKILL.md $(HELPER_SRCS)
	@mkdir -p $(DIST_DIR) $(BUILD_DIR)
	@rm -rf $(BUILD_DIR)/$*
	@mkdir -p $(BUILD_DIR)/$*/scripts
	@cp -R $(SKILL_DIR)/$*/. $(BUILD_DIR)/$*/
	@for h in $(HELPERS); do cp $(HELPER_DIR)/$$h $(BUILD_DIR)/$*/scripts/; done
	@rm -f $@
	@cd $(BUILD_DIR) && zip -r ../../$@ $* > /dev/null
	@rm -rf $(BUILD_DIR)/$*
	@echo "Wrote $@"

clean-skills:
	rm -rf $(DIST_DIR) $(BUILD_DIR)
