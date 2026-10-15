from pathlib import Path
import json
import re

root=Path(__file__).resolve().parents[1]
s=root/'skills/vitech-events-radar'
t=(s/'SKILL.md').read_text()
front=t.split('---',2)[1]
name=re.search(r'^name: (.+)$',front,re.M).group(1)
assert name==s.name and len(name)<=64 and re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',name)
desc=json.loads(re.search(r'^description: (.+)$',front,re.M).group(1))
assert 0<len(desc)<=300 and len(t.splitlines())<500 and len(t.encode())<=9000
for doc in [root/'README.md',root/'AGENTS.md',*s.rglob('*.md')]:
    for link in re.findall(r'\]\(([^)]+)\)',doc.read_text()):
        if '://' not in link and not link.startswith('#'):
            assert (doc.parent/link).is_file(),(doc,link)
for path in ('references/quality-rules.md','scripts/check_candidates.py','agents/openai.yaml',
             'assets/profile.example.json','references/devrel-contact.md','references/selection-flow.md',
             'assets/speaker-message.md','scripts/speaker_contact.py','scripts/research_audit.py',
             'references/monthly-digest.md','scripts/monthly_digest.py','references/tech-brands.json'):
    assert (s/path).is_file(),path
for old in ('assets/team-digest.md','assets/cfp-digest.md','references/speaker-support.md'):
    assert not (s/old).exists(),old
for f in s.rglob('*'):
    if f.is_file() and '__pycache__' not in f.parts and f.suffix in ('.md','.py','.json','.yaml'):
        assert 'TODO' not in f.read_text(),f
        assert 'mailto:' not in f.read_text(),f
version=(root/'VERSION').read_text().strip()
assert re.fullmatch(r'\d+\.\d+\.\d+',version)
assert f'v{version}' in (root/'README.md').read_text()
registry=json.loads((s/'references/tech-brands.json').read_text())
assert registry['source_url']=='https://habr.com/ru/specials/965986/'
brands=registry['brands']
assert isinstance(brands,list) and brands
assert all(isinstance(b.get('id'),str) and b['id'].strip() and isinstance(b.get('name'),str) and b['name'].strip() for b in brands)
assert len({b['id'] for b in brands})==len(brands)
assert len({b['name'].strip().casefold() for b in brands})==len(brands)
from datetime import date
assert date.fromisoformat(registry['refreshed_on'])<=date.today()
assert json.loads((s/'assets/profile.example.json').read_text())['languages']==['ru']
print('Structure, local references and personal distribution: OK')
