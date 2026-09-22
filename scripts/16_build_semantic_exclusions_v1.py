#!/usr/bin/env python3
from pathlib import Path
import json, csv, hashlib, argparse

EXCLUSIONS = [('NEGATED_OR_NON_DIVINE', 'غَافِل', 'Negative sentence: the Quran denies heedlessness/unawareness of God.'), ('NEGATED_OR_NON_DIVINE', 'ظَلَّام', 'Negative sentence: the Quran denies that God is extremely unjust / wronging.'), ('NEGATED_OR_NON_DIVINE', 'مَسْبُوق', 'Negative sentence: the Quran denies that God can be outstripped / forestalled.'), ('NEGATED_OR_NON_DIVINE', 'إِلَـٰه غَيْر', "Pharaoh's words about taking another deity; not a Quran-endorsed descriptor of the one God."), ('NEGATED_OR_NON_DIVINE', 'ظَالِم', 'Negative sentence: the Quran denies wrongdoing / injustice of God.'), ('NEGATED_OR_NON_DIVINE', 'غَائِب', 'Negative sentence: the Quran denies absence.'), ('NEGATED_OR_NON_DIVINE', 'فَقِير', 'False hostile attribution reported from others: they say that God is poor/needy.'), ('NEGATED_OR_NON_DIVINE', 'لَاعِب', "Negative sentence: the Quran denies that God's creation is play."), ('NEGATED_OR_NON_DIVINE', 'نَسِيّ', "Negative sentence: 'your Lord is not forgetful'; the denied predicate must not become a descriptor."), ('BODY_PART_RHETORICAL', 'يَد', 'Human body-part term used rhetorically/analogically; excluded as a standalone definition of God.'), ('BODY_PART_RHETORICAL', 'عَيْن', 'Human body-part term used rhetorically/analogically; excluded as a standalone definition of God.'), ('BODY_PART_RHETORICAL', 'وَجْه', 'Human body-part term used rhetorically/analogically; excluded as a standalone definition of God.'), ('TOO_SPECIFIC_CONTEXTUAL', 'إِلَـٰه مُوسَىٰ', "Pharaoh-context expression 'God of Moses'; too speaker-/context-specific for the descriptor inventory."), ('TOO_SPECIFIC_CONTEXTUAL', 'رَبّ مُوسَىٰ وَهَارُون', "Believers' expression 'Lord of Moses and Aaron'; valid in context but too specific for the retained descriptor inventory."), ('TOO_SPECIFIC_CONTEXTUAL', 'رَبّ هَارُون وَمُوسَىٰ', 'Context-specific contrast identifying the one true God worshipped by Aaron and Moses; too specific for the retained descriptor inventory.'), ('TOO_GENERAL', 'جَاعِل', "Too general as a standalone identity ('maker/one who makes'); excluded from the curated descriptor set."), ('TOO_GENERAL', 'فَاعِل', "Too general as a standalone identity ('doer'); excluded from the curated descriptor set."), ('TOO_GENERAL', 'فَعَّال', "Too general as a standalone identity ('effecter/doer'); excluded from the curated descriptor set."), ('OTHER_SCOPE', 'عِزَّة', "Abstract noun 'might/honor', not an explicit standalone descriptor; the related descriptor ʿAzīz already covers the concept."), ('OTHER_SCOPE', 'نَفْس', "Functions as self-reference ('Himself/Myself') rather than as an independent descriptor."), ('ORDINAL_RELATIONAL', 'رَابِع', "Relational ordinal in a passage about God's presence with a group; not a rank or standalone divine descriptor."), ('ORDINAL_RELATIONAL', 'سَادِس', "Relational ordinal in a passage about God's presence with a group; not a rank or standalone divine descriptor.")]

def load(p): return json.loads(p.read_text(encoding="utf-8"))
def dump(p,o): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(o,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
def sha(p):
    h=hashlib.sha256();
    with p.open("rb") as f:
        for c in iter(lambda:f.read(1048576),b""): h.update(c)
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--repo",type=Path,default=Path(__file__).resolve().parents[1]); ap.add_argument("--overwrite",action="store_true"); a=ap.parse_args()
    repo=a.repo.resolve(); src=repo/"runs/phase1_full_v3_2_1/phase2_global_audit_sol_v3"; out=repo/"runs/phase1_full_v3_2_1/semantic_exclusions_v1"
    if out.exists() and any(out.iterdir()) and not a.overwrite: raise SystemExit(f"Output exists: {out}\nUse --overwrite only to intentionally regenerate this derived version.")
    paths={"surface_map":src/"surface_to_lexeme_map_reviewed.json","groups":src/"lexical_groups_reviewed.json","occurrences":src/"descriptor_occurrences_lexical.json","frequency":src/"lexical_frequency.json"}
    for p in paths.values():
        if not p.exists(): raise SystemExit(f"Missing source: {p}")
    sm,gd,od,fd=[load(paths[k]) for k in ["surface_map","groups","occurrences","frequency"]]
    excluded={x[1] for x in EXCLUSIONS}; gb={x["lexical_identity_arabic"]:x for x in gd["groups"]}; ob={}
    for o in od["occurrences"]: ob.setdefault(o["lexical_identity_arabic"],[]).append(o)
    missing=excluded-{x["lexical_identity_arabic"] for x in fd["lexical_identities"]}
    if missing: raise SystemExit(f"Missing requested identities: {sorted(missing)}")
    records=[]; exocc=[]
    for i,(cat,ident,reason) in enumerate(EXCLUSIONS,1):
        occs=ob.get(ident,[]); ss=gb[ident]["member_surfaces"]; rec={"decision_id":f"SEMEX-V1-{i:03d}","lexical_identity_arabic":ident,"category":cat,"decision":"EXCLUDE","rationale":reason,"occurrence_count":len(occs),"exact_surface_count":len(ss),"member_surfaces":ss,"verse_keys":[o["verse_key"] for o in occs],"occurrence_ids":[o["occurrence_id"] for o in occs]}; records.append(rec)
        for o in occs: exocc.append({**o,"semantic_exclusion_decision_id":rec["decision_id"],"semantic_exclusion_category":cat,"semantic_exclusion_rationale":reason})
    occ=[o for o in od["occurrences"] if o["lexical_identity_arabic"] not in excluded]; groups=[g for g in gd["groups"] if g["lexical_identity_arabic"] not in excluded]; mappings=[m for m in sm["mappings"] if m["lexical_identity_arabic"] not in excluded]
    ctr={}
    for o in occ: ctr[o["lexical_identity_arabic"]]=ctr.get(o["lexical_identity_arabic"],0)+1
    freq=[]
    for old in fd["lexical_identities"]:
        ident=old["lexical_identity_arabic"]
        if ident in excluded: continue
        ss=gb[ident]["member_surfaces"]; freq.append({"lexical_identity_arabic":ident,"occurrence_count":ctr.get(ident,0),"exact_surface_count":len(ss),"member_surfaces":ss})
    exsurf={s for r in records for s in r["member_surfaces"]}
    checks=(len(records),len(exocc),len(exsurf),len(freq),len(occ),len(mappings),len(groups))
    if checks!=(22,50,31,233,5067,415,233): raise SystemExit(f"Count validation failed: {checks}")
    V="semantic-exclusions-v1"; R="phase1_full_v3_2_1_semantic_exclusions_v1"
    dump(out/"surface_to_lexeme_map_reviewed.json",{"version":V,"source_version":sm["version"],"run_name":R,"semantic_exclusion_manifest":"semantic_exclusions_manifest.json","surface_count":415,"lexical_identity_count":233,"mappings":mappings})
    dump(out/"lexical_groups_reviewed.json",{"version":V,"source_version":gd["version"],"run_name":R,"semantic_exclusion_manifest":"semantic_exclusions_manifest.json","surface_count":415,"lexical_identity_count":233,"groups":groups})
    dump(out/"descriptor_occurrences_lexical.json",{"version":V,"source_version":od["version"],"run_name":R,"semantic_exclusion_manifest":"semantic_exclusions_manifest.json","occurrence_count":5067,"occurrences":occ})
    dump(out/"lexical_frequency.json",{"version":V,"source_version":fd["version"],"run_name":R,"semantic_exclusion_manifest":"semantic_exclusions_manifest.json","lexical_identity_count":233,"total_occurrences":5067,"lexical_identities":freq})
    dump(out/"excluded_descriptors.json",{"version":V,"excluded_identity_count":22,"excluded_occurrence_count":50,"excluded_exact_surface_count":31,"exclusions":records})
    dump(out/"excluded_occurrences.json",{"version":V,"occurrence_count":50,"occurrences":exocc})
    dump(out/"semantic_exclusions_manifest.json",{"version":V,"date":"2026-09-13","kind":"semantic_exclusion_revision","policy":{"original_phase2_files_modified":False,"operation":"identity-level exclusion followed by deterministic filtering/recounting"},"source":{"authoritative_directory":str(src.relative_to(repo)),"input_counts":{"lexical_identities":255,"occurrences":5117,"exact_surfaces":446},"input_sha256":{k:sha(v) for k,v in paths.items()}},"result":{"output_directory":str(out.relative_to(repo)),"lexical_identities":233,"occurrences":5067,"exact_surfaces":415},"exclusions":records})
    with (out/"excluded_descriptors.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.writer(f); w.writerow(["decision_id","arabic","category","decision","occurrence_count","exact_surface_count","verse_keys","rationale"]); [w.writerow([r["decision_id"],r["lexical_identity_arabic"],r["category"],"EXCLUDE",r["occurrence_count"],r["exact_surface_count"],", ".join(r["verse_keys"]),r["rationale"]]) for r in records]
    print("SEMANTIC EXCLUSIONS V1: PASS"); print("255 -> 233 identities"); print("5117 -> 5067 occurrences"); print("446 -> 415 exact surfaces"); print(f"Output: {out}")
if __name__=="__main__": main()
