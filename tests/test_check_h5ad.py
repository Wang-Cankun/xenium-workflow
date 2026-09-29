import tempfile, importlib.util, pathlib, numpy as np, h5py, json
from unittest.mock import patch
from types import SimpleNamespace
spec=importlib.util.spec_from_file_location('check_h5ad',str(pathlib.Path(__file__).resolve().parents[1]/'skills/xenium-analysis-input-check/scripts/check_h5ad.py')); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
with tempfile.TemporaryDirectory() as d:
 for encoding in ['array','csr_matrix','csc_matrix']:
  p=pathlib.Path(d)/('fixture_'+encoding+'.h5ad')
  with h5py.File(p,'w') as f:
   for name, ids in [('obs',['a','a','c']),('var',['g1','g2'])]:
    g=f.create_group(name); g.attrs['_index']='_index'; g.create_dataset('_index',data=ids)
   f['obs'].create_dataset('core',data=['one','two','two'])
   f.create_group('obsm').create_dataset('spatial',data=[[1.,2.],[1.,2.],[float('nan'),3.]])
   u=f.create_group('uns'); u.create_dataset('nullable',data=h5py.Empty('f'))
   if encoding=='array': f.create_dataset('X',data=[[1.,0.],[0.,0.],[0.,-0.5]])
   else:
    g=f.create_group('X'); g.attrs['shape']=[3,2]; g.attrs['encoding-type']=encoding
    g.create_dataset('data',data=[1.,-0.5]); g.create_dataset('indices',data=[0,1] if encoding=='csr_matrix' else [0,2]); g.create_dataset('indptr',data=[0,1,1,2] if encoding=='csr_matrix' else [0,1,2])
  x=mod.inspect_file(p,full=True,specimen_key='core',id_columns=['_index'])
  assert x['matrices']['X']['empty_rows']==1
  assert x['matrices']['X']['negative']==1 and x['matrices']['X']['fractional']==1
  assert not x['obs_index']['unique']
  assert x['identity_checks']['_index']['within_specimen_duplicate_rows']==0
  assert x['spatial']['nonfinite']==1
  assert x['spatial']['overall']['duplicate_coordinate_rows']==1
  assert x['spatial']['by_specimen']['one']['duplicate_coordinate_rows']==0
  assert x['uns']['nullable'] is None
  json.dumps(x,allow_nan=False)
  def broken_reader(*args,**kwargs):
   raise RuntimeError('synthetic reader failure')
  with patch.dict('sys.modules', {'anndata': SimpleNamespace(read_h5ad=broken_reader)}):
   failed=mod.inspect_file(p,check_anndata=True)
   assert not failed['anndata_read']['success']
   assert 'anndata_read: synthetic reader failure' in failed['errors']
  if encoding!='array':
   with h5py.File(p,'r+') as f:f['X/indptr'][-1]=100
   bad=mod.inspect_file(p,full=True)
   assert bad['errors'] and not bad['matrices']['X']['structure_valid']
print('Synthetic dense/CSR/CSC, scoped IDs, missing coordinates, null metadata and invalid sparse pointers: passed')
