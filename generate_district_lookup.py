import csv, json, os, re, sys

NCES_NAME  = 1
NCES_CITY  = 4
NCES_STATE = 5
NCES_LAT   = 10
NCES_LON   = 11

def load_nces(path):
    districts = []
    with open(path, encoding='utf-8-sig', errors='replace') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) < 12:
                continue
            try:
                lat = float(parts[NCES_LAT])
                lon = float(parts[NCES_LON])
            except (ValueError, IndexError):
                continue
            districts.append({
                'name':  parts[NCES_NAME].strip(),
                'city':  parts[NCES_CITY].strip(),
                'state': parts[NCES_STATE].strip().upper(),
                'lat':   lat,
                'lon':   lon,
            })
    state_index = {}
    for d in districts:
        state_index.setdefault(d['state'], []).append(d)
    print("  Loaded " + str(len(districts)) + " NCES districts across " + str(len(state_index)) + " states")
    return state_index

def norm(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())

def search(prefix, state, state_index, method):
    np = norm(prefix)
    if len(np) < 2:
        return None
    best = None
    best_score = 0.0
    for d in state_index.get(state, []):
        nd = norm(d['name'])
        if np in nd:
            score = len(np) / max(len(nd), 1)
            if score > best_score:
                best_score = score
                best = d
    if best and best_score >= 0.15:
        return {**best, 'method': method}
    return None

def match(domain, state, state_index):
    domain = domain.lower().strip()
    m = re.match(r'^(.+?)\.k12\.([a-z]{2})\.us$', domain)
    if m:
        r = search(m.group(1), m.group(2).upper(), state_index, 'k12')
        if r:
            return r
    for itype in ['isd','usd','cusd','pusd','csd','rsd','ccsd','bcsd','asd','msd']:
        m = re.match(r'^(.+?)' + itype + r'[\.\-]', domain)
        if not m:
            base = domain.split('.')[0]
            m = re.match(r'^(.+?)' + itype + r'$', base)
        if m:
            prefix = m.group(1).rstrip('-').rstrip('.')
            if state and len(norm(prefix)) >= 3:
                r = search(prefix, state.upper(), state_index, itype)
                if r:
                    return r
            break
    if state:
        base = norm(domain.split('.')[0])
        if len(base) >= 4:
            for d in state_index.get(state.upper(), []):
                if base == norm(d['city']):
                    return {**d, 'method': 'city_match'}
    return None

def load_domains(csv_path):
    domain_states = {}
    with open(csv_path, encoding='utf-8-sig', errors='replace') as f:
        reader = csv.reader(f)
        headers = [h.strip() for h in next(reader)]
        def find(target):
            for i, h in enumerate(headers):
                if h == target:
                    return i
            return None
        ie = find('col_3') or 3
        il = find('col_7') or 7
        is_ = find('col_11') or 11
        personal = {'gmail.com','yahoo.com','hotmail.com','outlook.com',
                    'icloud.com','me.com','aol.com','comcast.net','att.net',
                    'verizon.net','live.com','msn.com',
                    'theartofeducation.edu','students.theartofeducation.edu'}
        for row in reader:
            if len(row) <= max(ie, il, is_):
                continue
            email = (row[ie] or '').strip().lower()
            loc   = (row[il] or '').strip()
            state = (row[is_] or '').strip().upper()
            if loc or not email or '@' not in email:
                continue
            domain = email.split('@')[-1]
            if domain in personal:
                continue
            if domain not in domain_states:
                domain_states[domain] = {}
            if state:
                domain_states[domain][state] = domain_states[domain].get(state, 0) + 1
    result = []
    for domain, sc in domain_states.items():
        best_state = max(sc, key=sc.get) if sc else None
        result.append((domain, best_state))
    print("  Found " + str(len(result)) + " unique institutional domains")
    return result

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 generate_district_lookup.py nces_districts.txt members_import.csv")
        sys.exit(1)
    print("=== AOEU Member Map: generate_district_lookup.py ===\n")
    print("[1/3] Loading NCES district data...")
    state_index = load_nces(sys.argv[1])
    print("\n[2/3] Extracting member email domains...")
    domains = load_domains(sys.argv[2])
    print("\n[3/3] Matching domains to districts...")
    lookup = {}
    stats = {'k12': 0, 'isd': 0, 'city': 0, 'none': 0}
    for domain, state in domains:
        r = match(domain, state, state_index)
        if r:
            lookup[domain] = {
                'lat':   round(r['lat'], 5),
                'lng':   round(r['lon'], 5),
                'city':  r['city'],
                'state': r['state'],
                'name':  r['name'],
            }
            m = r.get('method','')
            if 'k12' in m:
                stats['k12'] += 1
            elif any(x in m for x in ['isd','usd','csd','asd','msd']):
                stats['isd'] += 1
            else:
                stats['city'] += 1
        else:
            stats['none'] += 1
    with open('district_lookup.json', 'w') as f:
        json.dump(lookup, f, indent=2)
    total = len(lookup)
    rate  = round(total / len(domains) * 100, 1) if domains else 0
    print("\n" + "="*50)
    print("  Domains processed:      " + str(len(domains)))
    print("  Matched via .k12 URL:   " + str(stats['k12']))
    print("  Matched via ISD/USD:    " + str(stats['isd']))
    print("  Matched via city name:  " + str(stats['city']))
    print("  No match found:         " + str(stats['none']))
    print("  " + "-"*46)
    print("  Total domains matched:  " + str(total) + "  (" + str(rate) + "%)")
    print("  Written to: district_lookup.json")
    print("="*50)

if __name__ == '__main__':
    main()