#!/bin/bash
# Script to push wiki documentation to GitHub

echo "=== GitHub Wiki Push Script ==="
echo ""
echo "IMPORTANT: Before running this script, you need to:"
echo "1. Go to https://github.com/adapdoaosdaoda/asdas-cogs/wiki"
echo "2. Click 'Create the first page'"
echo "3. Add any content (it will be replaced)"
echo "4. Click 'Save Page'"
echo ""
echo "This initializes the wiki repository on GitHub."
echo ""
read -p "Have you initialized the wiki on GitHub? (y/n) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Please initialize the wiki first, then run this script again."
    exit 1
fi

echo "Proceeding with wiki push..."
echo ""

# Clone the wiki repository
cd /tmp
rm -rf asdas-cogs-wiki
git clone https://github.com/adapdoaosdaoda/asdas-cogs.wiki.git asdas-cogs-wiki

# Copy wiki files
cd asdas-cogs-wiki
cp -r ~/asdas-cogs/wiki/* .

# Flatten directory structure for GitHub wiki
for file in EventChannels/*.md; do
  [ -f "$file" ] && mv "$file" "EventChannels-$(basename "$file")"
done
[ -d EventChannels ] && rmdir EventChannels

for file in EventRoleReadd/*.md; do
  [ -f "$file" ] && mv "$file" "EventRoleReadd-$(basename "$file")"
done
[ -d EventRoleReadd ] && rmdir EventRoleReadd

for file in Reminders/*.md; do
  [ -f "$file" ] && mv "$file" "Reminders-$(basename "$file")"
done
[ -d Reminders ] && rmdir Reminders

# Update all links to flat structure
find . -name "*.md" -type f -exec sed -i \
  -e 's|\](EventChannels/Overview)|\](EventChannels-Overview)|g' \
  -e 's|\](EventChannels/Getting-Started)|\](EventChannels-Getting-Started)|g' \
  -e 's|\](EventChannels/Commands-Reference)|\](EventChannels-Commands-Reference)|g' \
  -e 's|\](EventChannels/Voice-Multipliers)|\](EventChannels-Voice-Multipliers)|g' \
  -e 's|\](EventChannels/Minimum-Roles-Enforcement)|\](EventChannels-Minimum-Roles-Enforcement)|g' \
  -e 's|\](EventChannels/Channel-Customization)|\](EventChannels-Channel-Customization)|g' \
  -e 's|\](EventChannels/Configuration-Examples)|\](EventChannels-Configuration-Examples)|g' \
  -e 's|\](EventChannels/Troubleshooting)|\](EventChannels-Troubleshooting)|g' \
  -e 's|\](EventChannels/Technical-Details)|\](EventChannels-Technical-Details)|g' \
  -e 's|\](EventRoleReadd/Overview)|\](EventRoleReadd-Overview)|g' \
  -e 's|\](EventRoleReadd/Commands-Reference)|\](EventRoleReadd-Commands-Reference)|g' \
  -e 's|\](Reminders/Overview)|\](Reminders-Overview)|g' \
  -e 's|\](Reminders/Commands-Reference)|\](Reminders-Commands-Reference)|g' \
  -e 's|\](../Home)|\](Home)|g' \
  -e 's|\](Getting-Started)|\](EventChannels-Getting-Started)|g' \
  -e 's|\](Overview)|\](EventChannels-Overview)|g' \
  -e 's|\](Commands-Reference)|\](EventChannels-Commands-Reference)|g' \
  {} \;

# Commit and push
git add .
git commit -m "docs: Initialize comprehensive wiki documentation

Complete restructuring of all cog documentation into wiki format.

Pages created:
- Home: Central navigation hub
- Installation: Setup guide

EventChannels (9 pages):
- Overview, Getting Started, Commands Reference
- Voice Multipliers, Minimum Roles Enforcement
- Channel Customization, Configuration Examples
- Troubleshooting, Technical Details

EventRoleReadd (2 pages):
- Overview, Commands Reference

Reminders (2 pages):
- Overview, Commands Reference

All pages include cross-links, examples, and comprehensive guides."

git push origin master

echo ""
echo "✅ Wiki pushed successfully!"
echo "View it at: https://github.com/adapdoaosdaoda/asdas-cogs/wiki"
