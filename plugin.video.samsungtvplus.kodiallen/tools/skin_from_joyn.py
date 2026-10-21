# -*- coding: utf-8 -*-
"""Derive the Samsung TV Plus window XMLs from the Kodi Allen Joyn add-on's.

The Joyn windows are the Tubi layouts with Joyn's navbar; this carries them
over for a live-only add-on: Samsung blue instead of Joyn teal, the navbar
Home / Live TV / Search with the region shown as a label, and Home's poster
rows replaced by landscape channel tiles (what is on now, the channel's logo,
its name, the programme title and its progress).

    python3 tools/skin_from_joyn.py <path to plugin.video.joyn.kodiallen> <output dir>
"""
import os
import re
import sys

FILES = {'JoynHome.xml': 'StvHome.xml', 'JoynLive.xml': 'StvLive.xml',
         'JoynLoading.xml': 'StvLoading.xml', 'JoynSearch.xml': 'StvSearch.xml'}
COLOURS = {'FF00E1C1': 'FF4C8DFF', 'FF007F73': 'FF1F4FCC', 'A6006B62': 'A6143E99', 'FF005A52': 'FF16378A'}
ADDON = 'plugin.video.samsungtvplus.kodiallen'
ENTRIES = ((301, 30210), (302, 30211), (303, 30203))
# Joyn navbar id -> Samsung navbar id where a page points UP or DOWN into it.
NAVBAR = {'301': '301', '302': '302', '303': '301', '304': '301', '305': '301', '306': '303', '307': '303'}
REGION_PROPERTY = {'StvHome.xml': 'stv.region', 'StvLive.xml': 'stv.live.region', 'StvSearch.xml': 'stv.search.region'}


def navbar(down, regionProperty):
    out = ['''        <control type="grouplist" id="9300">
            <left>264</left><top>20</top><width>1160</width><height>40</height>
            <orientation>horizontal</orientation><itemgap>37</itemgap>
            <ondown>%s</ondown>''' % down]
    for controlId, stringId in ENTRIES:
        out.append('''            <control type="button" id="%d">
                <width>auto</width><height>40</height>
                <texturefocus border="0,0,0,3">stv-underline.png</texturefocus><texturenofocus />
                <label>$ADDON[%s %d]</label><font>font13</font><textoffsetx>0</textoffsetx><aligny>center</aligny>
                <textcolor>FFC0C0C0</textcolor><focusedcolor>FFF0F0F0</focusedcolor>
                <ondown>%s</ondown>
            </control>''' % (controlId, ADDON, stringId, down))
    out.append('        </control>')
    out.append('''        <control type="label">
            <left>1440</left><top>20</top><width>380</width><height>40</height>
            <label>[B]$INFO[Window.Property(%s)][/B]</label><font>font13</font>
            <align>right</align><aligny>center</aligny><textcolor>FFC0C0C0</textcolor>
        </control>''' % regionProperty)
    return '\n'.join(out)


TILE = '''<itemlayout width="432" height="316">
                        <control type="image">
                            <left>4</left><top>4</top><width>400</width><height>225</height>
                            <texture colordiffuse="FF252830">stv-white.png</texture>
                        </control>
                        <control type="image">
                            <left>4</left><top>4</top><width>400</width><height>225</height>
                            <aspectratio>scale</aspectratio>
                            <texture background="true">$INFO[ListItem.Art(landscape)]</texture>
                        </control>
                        <control type="image">
                            <left>14</left><top>159</top><width>64</width><height>64</height>
                            <aspectratio>keep</aspectratio>
                            <texture background="true">$INFO[ListItem.Art(clearlogo)]</texture>
                        </control>
                        <control type="progress">
                            <left>4</left><top>225</top><width>400</width><height>4</height>
                            <texturebg colordiffuse="66000000">stv-white.png</texturebg>
                            <midtexture colordiffuse="FF4C8DFF">stv-white.png</midtexture>
                            <info>ListItem.Property(stv.progress)</info>
                        </control>
                        <control type="label">
                            <left>4</left><top>236</top><width>400</width><height>32</height>
                            <font>font12</font><textcolor>FFF0F0F0</textcolor>
                            <label>[B]$INFO[ListItem.Label][/B]</label>
                        </control>
                        <control type="label">
                            <left>4</left><top>268</top><width>400</width><height>32</height>
                            <font>font12</font><textcolor>FFA4A9B4</textcolor>
                            <label>$INFO[ListItem.Label2]</label>
                        </control>
                    </itemlayout>
                    <focusedlayout width="432" height="316">
                        <control type="image">
                            <left>0</left><top>0</top><width>408</width><height>233</height>
                            <texture colordiffuse="FFF0F0F0">stv-white.png</texture>
                            <visible>Control.HasFocus({id})</visible>
                        </control>
                        <control type="image">
                            <left>4</left><top>4</top><width>400</width><height>225</height>
                            <texture colordiffuse="FF252830">stv-white.png</texture>
                        </control>
                        <control type="image">
                            <left>4</left><top>4</top><width>400</width><height>225</height>
                            <aspectratio>scale</aspectratio>
                            <texture background="true">$INFO[ListItem.Art(landscape)]</texture>
                        </control>
                        <control type="image">
                            <left>14</left><top>159</top><width>64</width><height>64</height>
                            <aspectratio>keep</aspectratio>
                            <texture background="true">$INFO[ListItem.Art(clearlogo)]</texture>
                        </control>
                        <control type="progress">
                            <left>4</left><top>225</top><width>400</width><height>4</height>
                            <texturebg colordiffuse="66000000">stv-white.png</texturebg>
                            <midtexture colordiffuse="FF4C8DFF">stv-white.png</midtexture>
                            <info>ListItem.Property(stv.progress)</info>
                        </control>
                        <control type="label">
                            <left>4</left><top>236</top><width>400</width><height>32</height>
                            <font>font12</font><textcolor>FFF0F0F0</textcolor>
                            <label>[B]$INFO[ListItem.Label][/B]</label>
                        </control>
                        <control type="label">
                            <left>4</left><top>268</top><width>400</width><height>32</height>
                            <font>font12</font><textcolor>FFA4A9B4</textcolor>
                            <label>$INFO[ListItem.Label2]</label>
                        </control>
                    </focusedlayout>'''


def landscapeRows(text):
    """Home's four poster rows as rows of landscape channel tiles."""
    for listId in ('100', '110', '120', '130'):
        start = text.index('<control type="list" id="%s">' % listId)
        layoutStart = text.index('<itemlayout', start)
        layoutEnd = text.index('</focusedlayout>', layoutStart) + len('</focusedlayout>')
        text = text[:layoutStart] + TILE.replace('{id}', listId) + text[layoutEnd:]
        listEnd = text.index('<itemlayout', start)
        head = text[start:listEnd].replace('<height>476</height>', '<height>340</height>')
        head = head.replace('<onup condition="Integer.IsLess(Container(100).Position,3)">201</onup>',
                            '<onup condition="Integer.IsLess(Container(100).Position,2)">201</onup>')
        text = text[:start] + head + text[listEnd:]
    # The row groups shrink with their tiles.
    return text.replace('<height>532</height>', '<height>396</height>')


def convert(text, name):
    for old, new in COLOURS.items():
        text = text.replace(old, new)
    text = re.sub(r'joyn-(white|card-mask|ambient|logo|underline)\.png', r'stv-\1.png', text)
    text = text.replace('joyn.', 'stv.').replace('Joyn', 'Samsung TV Plus')
    start = text.find('<control type="grouplist" id="9300">')
    if start >= 0:
        start = text.rfind('\n', 0, start) + 1
        end = text.index('</control>', text.index('<control type="button" id="307">', start)) + len('</control>')
        down = re.search(r'<ondown>([^<]+)</ondown>', text[start:end]).group(1)
        remap = lambda match: '%s%s%s' % (match.group(1), NAVBAR[match.group(2)], match.group(3))
        pattern = re.compile(r'(<(?:onup|ondown|onleft|onright|defaultcontrol)[^>]*>)(30[1-7])(</)')
        text = pattern.sub(remap, text[:start]) + navbar(down, REGION_PROPERTY[name]) + pattern.sub(remap, text[end:])
    # The TV Plus wordmark is wider than Joyn's.
    text = text.replace('<left>100</left><top>24</top><width>76</width><height>32</height>',
                        '<left>100</left><top>24</top><width>142</width><height>32</height>')
    if name == 'StvHome.xml':
        text = landscapeRows(text)
    return text


def main(joyn, output):
    source = os.path.join(joyn, 'resources', 'skins', 'Default', '1080i')
    for joynName, name in FILES.items():
        with open(os.path.join(source, joynName), 'r') as handle:
            text = handle.read()
        with open(os.path.join(output, name), 'w') as handle:
            handle.write(convert(text, name))
        print(name)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
