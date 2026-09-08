import yaml
with open(r'C:\Users\Ratanshila\.openclaw\workspace\.github\workflows\ci.yml', 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f)
jobs = data.get('jobs', {})
print('Jobs found:', list(jobs.keys()))
for name, job in jobs.items():
    job_name = job.get('name', 'N/A')
    print('  {}: {}'.format(name, job_name))