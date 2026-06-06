LeadGen AI — App Icons
======================

This folder me PWA install ke liye app icons rakhe jaate hain.

Required PNG files (abhi placeholder SVG diya gaya hai — final PNG add karein):

  1. icon-192.png   -> 192 x 192 px
  2. icon-512.png   -> 512 x 512 px

Design guidelines:
  - Background: indigo / violet (#4f46e5)
  - Foreground: WHITE phone + AI / sound-wave motif (call + voice agent ka symbol)
  - Safe area: keep the main motif within the centre 80% (maskable icons ke liye),
    taaki Android/iOS rounded-corner crop me icon cut na ho.
  - PNG should be flat, no transparency on the maskable background.

Quick way to generate PNGs:
  - icon.svg (is folder me already present) ko kisi bhi tool se export karo:
      * Online: svgtopng / cloudconvert / realfavicongenerator.net
      * CLI:    rsvg-convert -w 192 -h 192 icon.svg -o icon-192.png
                rsvg-convert -w 512 -h 512 icon.svg -o icon-512.png
      * Inkscape: inkscape icon.svg -w 192 -h 192 -o icon-192.png

manifest.json icon-192.png, icon-512.png aur icon.svg teeno ko reference karta hai.
Jab tak PNG nahi banate, SVG fallback se bhi install/preview chal jaayega.
