# Wiki Documentation

This directory contains comprehensive wiki documentation for all cogs.

## 📋 Current Status

✅ **Local wiki files created** - All documentation pages are ready
⏳ **GitHub wiki push pending** - Requires manual initialization

## 🚀 How to Push to GitHub Wiki

### Option 1: Using the Automated Script

1. **Initialize the wiki on GitHub** (one-time setup):
   - Go to https://github.com/adapdoaosdaoda/asdas-cogs/wiki
   - Click "Create the first page"
   - Add any content (it will be replaced)
   - Click "Save Page"

2. **Run the push script**:
   ```bash
   cd /home/user/asdas-cogs
   ./push-wiki.sh
   ```

### Option 2: Manual Push

1. **Initialize wiki on GitHub** (see above)

2. **Clone the wiki repository**:
   ```bash
   git clone https://github.com/adapdoaosdaoda/asdas-cogs.wiki.git
   ```

3. **Copy and flatten the wiki files**:
   ```bash
   cd asdas-cogs.wiki

   # Copy files
   cp /home/user/asdas-cogs/wiki/*.md .

   # Flatten EventChannels
   for f in /home/user/asdas-cogs/wiki/EventChannels/*.md; do
     cp "$f" "EventChannels-$(basename "$f")"
   done

   # Flatten EventRoleReadd
   for f in /home/user/asdas-cogs/wiki/EventRoleReadd/*.md; do
     cp "$f" "EventRoleReadd-$(basename "$f")"
   done

   # Flatten Reminders
   for f in /home/user/asdas-cogs/wiki/Reminders/*.md; do
     cp "$f" "Reminders-$(basename "$f")"
   done
   ```

4. **Update links and push**:
   ```bash
   # Update all directory links to flat page names
   # (See push-wiki.sh for sed commands)

   git add .
   git commit -m "docs: Initialize comprehensive wiki"
   git push origin master
   ```

## 📚 Wiki Structure

### Created Pages

**Main:**
- `Home.md` - Central navigation
- `Installation.md` - Setup guide

**EventChannels (9 pages):**
- Overview, Getting Started, Commands Reference
- Voice Multipliers, Minimum Roles Enforcement
- Channel Customization, Configuration Examples
- Troubleshooting, Technical Details

**EventRoleReadd (2 pages):**
- Overview, Commands Reference

**Reminders (2 pages):**
- Overview, Commands Reference

### After Pushing to GitHub

Once pushed, the wiki will be available at:
**https://github.com/adapdoaosdaoda/asdas-cogs/wiki**

## 📝 Notes

- GitHub wikis don't support subdirectories, so pages are flattened with hyphens
- All cross-links have been updated to work with the flat structure
- The wiki files in this directory use subdirectories for local organization
- The push script automatically handles the conversion

## 🔄 Updating the Wiki

To update the wiki after making changes:

1. Edit the markdown files in this directory
2. Run `./push-wiki.sh` again
3. Or manually copy updated files to the cloned wiki repo and push

## ✅ Verification

After pushing, verify these pages exist:
- Home
- Installation
- EventChannels-Overview
- EventChannels-Getting-Started
- EventChannels-Commands-Reference
- EventChannels-Voice-Multipliers
- EventChannels-Minimum-Roles-Enforcement
- And 10 more pages...
