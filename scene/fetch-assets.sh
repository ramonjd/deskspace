#!/bin/sh
# Downloads the textures and fonts scene/cabin.py uses into scene/assets/.
# They aren't in git; run this once on a fresh checkout before building the scene.
#
# Textures: ambientCG, all CC0 1.0 (https://docs.ambientcg.com/license/), 1K JPG.
# Fonts: Google Fonts. Caveat and Anton are SIL Open Font License 1.1;
# Permanent Marker is Apache 2.0. Each licence file is saved next to its font.
set -eu
cd "$(dirname "$0")"

TEXTURES="
PaintedMetal012 walls: white paint over metal, chipped and rusty
Metal038 ribs, window frame, steel: scratched steel
Metal009 laptop: brushed, scratched aluminium
Rubber004 desk mat
Plastic013A sanitiser bottle, CD cases, phone
Paper006 post-it notes, poster, Morse card
Fabric061 notebook cover
Leather037 headphone cushions
Clay005 plant pot
DiamondPlate009 floor
SurfaceImperfections003 grime over walls and desk
Scratches005 scratches over metal and plastic
Fingerprints002 fingerprints on the laptop lid
Smear004 smudges on the window glass
Wood096 the guitar: bare wood under worn paint, and the maple neck
"

echo "$TEXTURES" | while read -r id rest; do
	[ -n "$id" ] || continue
	dir="assets/textures/$id"
	if [ -d "$dir" ]; then continue; fi
	mkdir -p "$dir"
	curl -sSfL "https://ambientcg.com/get?file=${id}_1K-JPG.zip" -o "$dir.zip"
	unzip -q "$dir.zip" -d "$dir"
	rm "$dir.zip"
	# Keep only the pictures: the packs also hold .blend and other scene files.
	find "$dir" -type f ! -name '*.jpg' -delete
	echo "texture $id"
done

font() {
	dir="assets/fonts/$1"
	if [ -d "$dir" ]; then return; fi
	mkdir -p "$dir"
	curl -sSfL "https://github.com/google/fonts/raw/main/$2" -o "$dir/$(basename "$2" | sed 's/%5B.*%5D//')"
	curl -sSfL "https://github.com/google/fonts/raw/main/$3" -o "$dir/$(basename "$3")"
	echo "font $1"
}
font caveat "ofl/caveat/Caveat%5Bwght%5D.ttf" "ofl/caveat/OFL.txt"
font permanent-marker "apache/permanentmarker/PermanentMarker-Regular.ttf" "apache/permanentmarker/LICENSE.txt"
font anton "ofl/anton/Anton-Regular.ttf" "ofl/anton/OFL.txt"
