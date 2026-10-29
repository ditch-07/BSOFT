from pathlib import Path
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parent.parent
source = ET.parse(root / 'static/img/nav-waves.svg').getroot()
ns = {'svg': 'http://www.w3.org/2000/svg'}
navy = source.find(".//svg:linearGradient[@id='base']/svg:stop[@offset='1']", ns).get('stop-color')
teal = source.find(".//svg:linearGradient[@id='contour']/svg:stop[@offset='0']", ns).get('stop-color')
contours = source.findall("svg:g[@class='c']/svg:path", ns)
lines = [
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1440 180" preserveAspectRatio="xMaxYMax slice">',
    '<rect width="1440" height="180" fill="#F5F6F3"/>',
    '<defs><linearGradient id="fade"><stop stop-color="white" stop-opacity="0"/><stop offset=".45" stop-color="white"/></linearGradient><mask id="right"><rect x="480" width="960" height="180" fill="url(#fade)"/></mask></defs>',
    '<g mask="url(#right)"><g transform="translate(480 100) scale(.5 1.1)" fill="none" stroke-width="1" stroke-linecap="round">',
]
for index, contour in enumerate(contours):
    color = navy if index % 3 == 0 else teal
    opacity = '.22' if index % 3 == 0 else '.15'
    lines.append(f'<path d="{contour.get("d")}" stroke="{color}" opacity="{opacity}" vector-effect="non-scaling-stroke"/>')
lines.append('</g></g></svg>')
(root / 'static/img/dashboard-waves.svg').write_text('\n'.join(lines) + '\n', encoding='utf-8')
