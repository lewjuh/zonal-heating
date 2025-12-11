# Zonal Heating HACS Integration - Version Management
# Usage:
#   make bump-patch    - Bump patch version (1.2.3 -> 1.2.4)
#   make bump-minor    - Bump minor version (1.2.3 -> 1.3.0)
#   make bump-major    - Bump major version (1.2.3 -> 2.0.0)
#   make release       - Bump patch and push to GitHub
#   make release-minor - Bump minor and push to GitHub
#   make release-major - Bump major and push to GitHub

MANIFEST := custom_components/zonal_heating/manifest.json
CURRENT_VERSION := $(shell grep -o '"version": "[^"]*"' $(MANIFEST) | cut -d'"' -f4)

# Parse version components
VERSION_MAJOR := $(shell echo $(CURRENT_VERSION) | cut -d. -f1)
VERSION_MINOR := $(shell echo $(CURRENT_VERSION) | cut -d. -f2)
VERSION_PATCH := $(shell echo $(CURRENT_VERSION) | cut -d. -f3)

# Calculate new versions
NEW_PATCH := $(shell echo $$(($(VERSION_PATCH) + 1)))
NEW_MINOR := $(shell echo $$(($(VERSION_MINOR) + 1)))
NEW_MAJOR := $(shell echo $$(($(VERSION_MAJOR) + 1)))

PATCH_VERSION := $(VERSION_MAJOR).$(VERSION_MINOR).$(NEW_PATCH)
MINOR_VERSION := $(VERSION_MAJOR).$(NEW_MINOR).0
MAJOR_VERSION := $(NEW_MAJOR).0.0

.PHONY: help version bump-patch bump-minor bump-major release release-minor release-major tag push

help:
	@echo "Zonal Heating Version Management"
	@echo ""
	@echo "Current version: $(CURRENT_VERSION)"
	@echo ""
	@echo "Commands:"
	@echo "  make version       - Show current version"
	@echo "  make bump-patch    - Bump to $(PATCH_VERSION)"
	@echo "  make bump-minor    - Bump to $(MINOR_VERSION)"
	@echo "  make bump-major    - Bump to $(MAJOR_VERSION)"
	@echo ""
	@echo "  make release       - Bump patch, commit, tag, and push"
	@echo "  make release-minor - Bump minor, commit, tag, and push"
	@echo "  make release-major - Bump major, commit, tag, and push"

version:
	@echo "Current version: $(CURRENT_VERSION)"
	@echo "  Patch bump -> $(PATCH_VERSION)"
	@echo "  Minor bump -> $(MINOR_VERSION)"
	@echo "  Major bump -> $(MAJOR_VERSION)"

bump-patch:
	@echo "Bumping version: $(CURRENT_VERSION) -> $(PATCH_VERSION)"
	@sed -i '' 's/"version": "$(CURRENT_VERSION)"/"version": "$(PATCH_VERSION)"/' $(MANIFEST)
	@echo "Updated $(MANIFEST)"

bump-minor:
	@echo "Bumping version: $(CURRENT_VERSION) -> $(MINOR_VERSION)"
	@sed -i '' 's/"version": "$(CURRENT_VERSION)"/"version": "$(MINOR_VERSION)"/' $(MANIFEST)
	@echo "Updated $(MANIFEST)"

bump-major:
	@echo "Bumping version: $(CURRENT_VERSION) -> $(MAJOR_VERSION)"
	@sed -i '' 's/"version": "$(CURRENT_VERSION)"/"version": "$(MAJOR_VERSION)"/' $(MANIFEST)
	@echo "Updated $(MANIFEST)"

commit-patch:
	@git add $(MANIFEST)
	@git commit -m "bump: $(PATCH_VERSION)"

commit-minor:
	@git add $(MANIFEST)
	@git commit -m "bump: $(MINOR_VERSION)"

commit-major:
	@git add $(MANIFEST)
	@git commit -m "bump: $(MAJOR_VERSION)"

tag-patch:
	@git tag -a "v$(PATCH_VERSION)" -m "Release v$(PATCH_VERSION)"
	@echo "Created tag: v$(PATCH_VERSION)"

tag-minor:
	@git tag -a "v$(MINOR_VERSION)" -m "Release v$(MINOR_VERSION)"
	@echo "Created tag: v$(MINOR_VERSION)"

tag-major:
	@git tag -a "v$(MAJOR_VERSION)" -m "Release v$(MAJOR_VERSION)"
	@echo "Created tag: v$(MAJOR_VERSION)"

push:
	@git push origin main
	@git push origin --tags
	@echo "Pushed to GitHub"

release: bump-patch commit-patch tag-patch push
	@echo ""
	@echo "Released v$(PATCH_VERSION)"

release-minor: bump-minor commit-minor tag-minor push
	@echo ""
	@echo "Released v$(MINOR_VERSION)"

release-major: bump-major commit-major tag-major push
	@echo ""
	@echo "Released v$(MAJOR_VERSION)"

# Dry run versions (show what would happen without making changes)
dry-run-patch:
	@echo "Would bump: $(CURRENT_VERSION) -> $(PATCH_VERSION)"
	@echo "Would commit: 'bump: $(PATCH_VERSION)'"
	@echo "Would tag: v$(PATCH_VERSION)"
	@echo "Would push to origin main with tags"

dry-run-minor:
	@echo "Would bump: $(CURRENT_VERSION) -> $(MINOR_VERSION)"
	@echo "Would commit: 'bump: $(MINOR_VERSION)'"
	@echo "Would tag: v$(MINOR_VERSION)"
	@echo "Would push to origin main with tags"

dry-run-major:
	@echo "Would bump: $(CURRENT_VERSION) -> $(MAJOR_VERSION)"
	@echo "Would commit: 'bump: $(MAJOR_VERSION)'"
	@echo "Would tag: v$(MAJOR_VERSION)"
	@echo "Would push to origin main with tags"
