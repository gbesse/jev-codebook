def assignment_prevalence_bounds(rows,codes):
 error='Affectations invalides / Invalid assignments / Asignaciones inválidas'
 if not isinstance(rows,list)or len(rows)>100000 or not isinstance(codes,list)or not codes or len(set(codes))!=len(codes)or any(not isinstance(c,str)or not c for c in codes):raise ValueError(error)
 seen=set();output=[]
 for r in rows:
  if not isinstance(r.get('id'),str)or not r['id']or r['id']in seen or type(r.get('review'))is not bool or not isinstance(r.get('assigned'),dict):raise ValueError(error)
  seen.add(r['id'])
  if any(k not in codes or type(v)not in(int,bool)or v not in(0,1)for k,v in r['assigned'].items()):raise ValueError(error)
 for code in codes:
  known=[r for r in rows if not r['review']and code in r['assigned']];positive=sum(bool(r['assigned'][code])for r in known);unknown=len(rows)-len(known)
  output.append({'code':code,'known_positive_assignments':positive,'known_negative_assignments':len(known)-positive,'unknown_assignments':unknown,'fraction_bounds':[positive/len(rows),(positive+unknown)/len(rows)]if rows else None})
 return {'codes':output,'population_prevalence_inferred':False,'pending_rows_assumed_negative':False}
