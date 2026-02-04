#!/bin/bash

# Log the call for debugging
echo "$(date): xdg-open called with '$*'" >> /tmp/xdg_hijack.log

# The first argument is the URL
URL="$1"

# Save it to the shared file
echo "$URL" > /tmp/cursor_login_url.txt

# Exit successfully so Cursor thinks it worked
exit 0
