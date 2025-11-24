# HACS Setup Guide for Zonal Heating

This guide will help you publish your Zonal Heating integration to GitHub and make it available through HACS.

## Prerequisites

- Git installed on your computer
- A GitHub account
- Your HACS-ready repository (already created in `~/zonal_heating_hacs`)

## Step 1: Create GitHub Repository

1. Go to [GitHub](https://github.com) and log in
2. Click the **+** icon in the top right → **New repository**
3. Repository settings:
   - **Name**: `zonal-heating` (or `homeassistant-zonal-heating`)
   - **Description**: "Intelligent multi-zone heating control for Home Assistant with TRV management"
   - **Visibility**: Public (required for HACS)
   - **Initialize**: Do NOT check "Add a README" (we already have one)
4. Click **Create repository**

## Step 2: Push Your Code to GitHub

Open a terminal and run these commands:

```bash
# Navigate to your HACS repository
cd ~/zonal_heating_hacs

# Initialize git repository
git init

# Add all files
git add .

# Create initial commit
git commit -m "Initial commit: Zonal Heating integration for Home Assistant"

# Add your GitHub repository as remote (replace YOUR_USERNAME)
git remote add origin https://github.com/YOUR_USERNAME/zonal-heating.git

# Push to GitHub
git branch -M main
git push -u origin main
```

**Note**: Replace `YOUR_USERNAME` with your actual GitHub username.

## Step 3: Create a Release

HACS requires at least one release:

1. Go to your repository on GitHub
2. Click **Releases** (right side of the page)
3. Click **Create a new release**
4. Fill in the details:
   - **Tag version**: `v1.0.0`
   - **Release title**: `v1.0.0 - Initial Release`
   - **Description**:
     ```
     Initial release of Zonal Heating integration

     Features:
     - Multi-zone heating support
     - Individual TRV control per room
     - Window detection and auto-pause
     - Priority-based heating (1-10)
     - Anti-cycling protection
     - Full UI configuration
     ```
5. Click **Publish release**

## Step 4: Validate HACS Compatibility

Your repository should now pass HACS validation. The GitHub workflow will automatically run and validate:
- HACS compatibility
- Home Assistant integration standards (hassfest)

Check the **Actions** tab in your repository to see if the validation passed.

## Step 5: Add to HACS (For Users)

### Option A: HACS Custom Repository (Immediate)

Users can add your integration immediately as a custom repository:

1. Open HACS in Home Assistant
2. Click the three dots (⋮) in the top right
3. Select **Custom repositories**
4. Add repository URL: `https://github.com/YOUR_USERNAME/zonal-heating`
5. Category: **Integration**
6. Click **Add**

### Option B: Default HACS Repository (Official)

To get your integration into the default HACS repository:

1. Your repository must meet all HACS requirements:
   - ✅ Public GitHub repository
   - ✅ At least one release
   - ✅ Passing HACS validation
   - ✅ README.md with installation instructions
   - ✅ hacs.json configuration
   - ✅ Proper repository structure

2. After ensuring all requirements are met, submit your integration:
   - Go to [HACS/default](https://github.com/hacs/default)
   - Read the [submission guidelines](https://hacs.xyz/docs/publish/integration)
   - Create a pull request to add your repository

3. Wait for HACS team review (can take several weeks)

## Step 6: Update Your Integration

When you make changes to your integration:

```bash
cd ~/zonal_heating_hacs

# Make your changes to the code
# ...

# Commit changes
git add .
git commit -m "Description of changes"
git push

# Create a new release on GitHub
# Tag: v1.0.1, v1.1.0, v2.0.0 (follow semantic versioning)
```

Users will see the update in HACS and can update with one click.

## Repository Structure

Your repository is now structured as:

```
zonal-heating/
├── .github/
│   └── workflows/
│       └── validate.yaml          # Automatic validation
├── custom_components/
│   └── zonal_heating/
│       ├── __init__.py
│       ├── climate.py
│       ├── config_flow.py
│       ├── const.py
│       ├── manifest.json
│       ├── quality_scale.yaml
│       ├── room_state_machine.py
│       ├── strings.json
│       ├── translations/
│       │   └── en.json
│       └── zone_state_machine.py
├── .gitignore
├── hacs.json                      # HACS configuration
├── info.md                        # HACS panel display
├── LICENSE
└── README.md                      # Main documentation
```

## Troubleshooting

### Validation Fails

Check the **Actions** tab in your GitHub repository to see what failed:
- HACS validation errors: Check `hacs.json` format
- Hassfest errors: Check `manifest.json` and integration structure

### Users Can't Find Integration

Make sure:
- Repository is public
- At least one release exists
- Users are adding the correct repository URL
- Category is set to "Integration" in HACS

### Updates Not Showing

- Create a new release on GitHub with a higher version number
- Users need to reload HACS or restart Home Assistant
- Check that the release tag follows semantic versioning (v1.0.0, v1.0.1, etc.)

## Next Steps

1. Test the integration thoroughly
2. Consider adding screenshots to README.md
3. Write detailed troubleshooting guides
4. Respond to issues and pull requests
5. Consider submitting to default HACS repository

## Support

If you need help:
- [HACS Documentation](https://hacs.xyz)
- [Home Assistant Developer Docs](https://developers.home-assistant.io)
- [HACS Discord](https://discord.gg/apgchf8)

Good luck with your integration! 🎉
