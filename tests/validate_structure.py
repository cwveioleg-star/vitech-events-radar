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
assert 0<len(desc)<=1024 and len(t.splitlines())<500
for doc in [root/'README.md',root/'AGENTS.md',*s.rglob('*.md')]:
    for link in re.findall(r'\]\(([^)]+)\)',doc.read_text()):
        if '://' not in link and not link.startswith('#'):
            assert (doc.parent/link).is_file(),(doc,link)
for path in ('references/quality-rules.md','scripts/check_candidates.py','agents/openai.yaml',
             'assets/profile.example.json','references/devrel-contact.md','references/selection-flow.md',
             'assets/speaker-message.md','scripts/speaker_contact.py','scripts/research_audit.py',
             'references/monthly-digest.md','scripts/monthly_digest.py'):
    assert (s/path).is_file(),path
for old in ('assets/team-digest.md','assets/cfp-digest.md','references/speaker-support.md'):
    assert not (s/old).exists(),old
for f in s.rglob('*'):
    if f.is_file() and '__pycache__' not in f.parts and f.suffix in ('.md','.py','.json','.yaml'):
        assert 'TODO' not in f.read_text(),f
        assert 'mailto:' not in f.read_text(),f
assert (root/'VERSION').read_text().strip()=='0.4.2'
assert 'v0.4.2' in (root/'README.md').read_text()
assert json.loads((s/'assets/profile.example.json').read_text())['languages']==['ru']
print('Structure, local references and personal distribution: OK')
