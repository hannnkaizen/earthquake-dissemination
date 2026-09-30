#!/bin/bash

awk -F'\n' -v RS='--------------------------------------------------\n' '
BEGIN {
    OFS = ","
    print "id,log_time,media_path,magnitude,event_time,latitude,longitude,location_description,depth,source"
}
NF {
    id = log_time = media = mag = ev_time = lat = lon = loc = depth = src = ""
    for (i = 1; i <= NF; i++) {
        if ($i ~ /^\[.*\] - ID:/) {
            match($i, /^\[(.*)\] - ID: ([0-9]+)/, m)
            log_time = m[1]; id = m[2]
        } else if ($i ~ /^Media/) {
            sub(/^Media[ \t]*:[ \t]*/, "", $i)
            media = $i
        } else if ($i ~ /^Content:/) {
            sub(/^Content:[ \t]*/, "", $i)
            if (match($i, /Mag:([0-9.]+), ([^,]+), Lok: ([0-9.]+ [A-Z]+) - ([0-9.]+ [A-Z]+) \(([^)]+)\), Kedlmn: ([0-9]+ km)( ::([A-Z]+))?/, c)) {
                mag = c[1]; ev_time = c[2]; lat = c[3]; lon = c[4]
                loc = "\"" c[5] "\""; depth = c[6]; src = (c[8] != "" ? c[8] : "BMKG")
            }
        }
    }
    if (id != "") {
        print id, log_time, media, mag, ev_time, lat, lon, loc, depth, src
    }
}' telegram_dissemination.txt > dissemination_parsed.csv