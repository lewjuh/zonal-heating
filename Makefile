# Zonal Heating HACS Integration - Version Management
# Usage:
#   make bump-patch    - Bump patch version (1.2.3 -> 1.2.4)
#   make bump-minor    - Bump minor version (1.2.3 -> 1.3.0)
#   make bump-major    - Bump major version (1.2.3 -> 2.0.0)
#   make release       - Bump patch and create GitHub release
#   make release-minor - Bump minor and create GitHub release
#   make release-major - Bump major and create GitHub release
#
# Release notes:
#   make release NOTES="Fixed bug with window sensors"
#   - Or leave NOTES empty to auto-generate from commits

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

# Optional release notes (pass via NOTES="your notes here")
NOTES ?=

.PHONY: help version bump-patch bump-minor bump-major release release-minor release-major

help:
	@echo "Zonal Heating Version Management"
	@echo ""
	@echo "Current version: $(CURRENT_VERSION)"
	@echo ""
	@echo "Commands:"
	@echo "  make version       - Show current version"
	@echo "  make bump-patch    - Bump to $(PATCH_VERSION) (local only)"
	@echo "  make bump-minor    - Bump to $(MINOR_VERSION) (local only)"
	@echo "  make bump-major    - Bump to $(MAJOR_VERSION) (local only)"
	@echo ""
	@echo "  make release       - Bump patch + commit + push + GitHub release"
	@echo "  make release-minor - Bump minor + commit + push + GitHub release"
	@echo "  make release-major - Bump major + commit + push + GitHub release"
	@echo ""
	@echo "  make gh-release    - Create GitHub release for current version"
	@echo ""
	@echo "Release notes (optional):"
	@echo "  make release NOTES=\"Your release notes here\""
	@echo "  - If NOTES is empty, auto-generates from commits"

version:
	@echo "Current version: $(CURRENT_VERSION)"
	@echo "  Patch bump -> $(PATCH_VERSION)"
	@echo "  Minor bump -> $(MINOR_VERSION)"
	@echo "  Major bump -> $(MAJOR_VERSION)"

# Local version bumps (no git operations)
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

# Create GitHub release for current version
gh-release:
	@echo "Creating GitHub release v$(CURRENT_VERSION)..."
ifeq ($(NOTES),)
	@gh release create "v$(CURRENT_VERSION)" \
		--title "v$(CURRENT_VERSION)" \
		--generate-notes \
		--latest
else
	@gh release create "v$(CURRENT_VERSION)" \
		--title "v$(CURRENT_VERSION)" \
		--notes "$(NOTES)" \
		--latest
endif
	@echo "GitHub release v$(CURRENT_VERSION) created!"

# Full release workflows
release:
	@echo "=== Creating patch release ==="
	@echo "Bumping version: $(CURRENT_VERSION) -> $(PATCH_VERSION)"
	@sed -i '' 's/"version": "$(CURRENT_VERSION)"/"version": "$(PATCH_VERSION)"/' $(MANIFEST)
	@git add $(MANIFEST)
	@git commit -m "bump: $(PATCH_VERSION)"
	@git push origin main
	@echo "Creating GitHub release v$(PATCH_VERSION)..."
ifeq ($(NOTES),)
	@gh release create "v$(PATCH_VERSION)" \
		--title "v$(PATCH_VERSION)" \
		--generate-notes \
		--latest
else
	@gh release create "v$(PATCH_VERSION)" \
		--title "v$(PATCH_VERSION)" \
		--notes "$(NOTES)" \
		--latest
endif
	@echo ""
	@echo "=== Released v$(PATCH_VERSION) ==="

release-minor:
	@echo "=== Creating minor release ==="
	@echo "Bumping version: $(CURRENT_VERSION) -> $(MINOR_VERSION)"
	@sed -i '' 's/"version": "$(CURRENT_VERSION)"/"version": "$(MINOR_VERSION)"/' $(MANIFEST)
	@git add $(MANIFEST)
	@git commit -m "bump: $(MINOR_VERSION)"
	@git push origin main
	@echo "Creating GitHub release v$(MINOR_VERSION)..."
ifeq ($(NOTES),)
	@gh release create "v$(MINOR_VERSION)" \
		--title "v$(MINOR_VERSION)" \
		--generate-notes \
		--latest
else
	@gh release create "v$(MINOR_VERSION)" \
		--title "v$(MINOR_VERSION)" \
		--notes "$(NOTES)" \
		--latest
endif
	@echo ""
	@echo "=== Released v$(MINOR_VERSION) ==="

release-major:
	@echo "=== Creating major release ==="
	@echo "Bumping version: $(CURRENT_VERSION) -> $(MAJOR_VERSION)"
	@sed -i '' 's/"version": "$(CURRENT_VERSION)"/"version": "$(MAJOR_VERSION)"/' $(MANIFEST)
	@git add $(MANIFEST)
	@git commit -m "bump: $(MAJOR_VERSION)"
	@git push origin main
	@echo "Creating GitHub release v$(MAJOR_VERSION)..."
ifeq ($(NOTES),)
	@gh release create "v$(MAJOR_VERSION)" \
		--title "v$(MAJOR_VERSION)" \
		--generate-notes \
		--latest
else
	@gh release create "v$(MAJOR_VERSION)" \
		--title "v$(MAJOR_VERSION)" \
		--notes "$(NOTES)" \
		--latest
endif
	@echo ""
	@echo "=== Released v$(MAJOR_VERSION) ==="

# Dry run versions (show what would happen without making changes)
dry-run:
	@echo "Would bump: $(CURRENT_VERSION) -> $(PATCH_VERSION)"
	@echo "Would commit: 'bump: $(PATCH_VERSION)'"
	@echo "Would push to origin main"
	@echo "Would create GitHub release: v$(PATCH_VERSION)"

dry-run-minor:
	@echo "Would bump: $(CURRENT_VERSION) -> $(MINOR_VERSION)"
	@echo "Would commit: 'bump: $(MINOR_VERSION)'"
	@echo "Would push to origin main"
	@echo "Would create GitHub release: v$(MINOR_VERSION)"

dry-run-major:
	@echo "Would bump: $(CURRENT_VERSION) -> $(MAJOR_VERSION)"
	@echo "Would commit: 'bump: $(MAJOR_VERSION)'"
	@echo "Would push to origin main"
	@echo "Would create GitHub release: v$(MAJOR_VERSION)"
