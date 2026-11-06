"""Extracts the treble clef (U+1D11E) outline from Noto Music as an SVG path (font units, y up)."""
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.boundsPen import BoundsPen

font = TTFont('tools/NotoMusic.ttf')
name = font.getBestCmap().get(0x1D11E)
glyphs = font.getGlyphSet()
pen, bounds = SVGPathPen(glyphs), BoundsPen(glyphs)
glyphs[name].draw(pen)
glyphs[name].draw(bounds)
path = pen.getCommands()
open('tools/clef-path.txt', 'w').write(path)
print('glyph', name, 'unitsPerEm', font['head'].unitsPerEm, 'bounds', bounds.bounds, 'path chars', len(path))
