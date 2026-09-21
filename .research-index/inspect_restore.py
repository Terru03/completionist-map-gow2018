import sys, sqlite3, importlib.util, struct
from pathlib import Path
root=Path.cwd()
sys.path.insert(0,str(root/'.research-index/python-packages'))
spec=importlib.util.spec_from_file_location('base',root/'tools/v0.10.5/trace-checkpoint-restore-bridge.py'); base=importlib.util.module_from_spec(spec); spec.loader.exec_module(base)
pe=base.PE(Path('G:/SteamLibrary/steamapps/common/GodOfWar/GoW.exe').read_bytes())
con=sqlite3.connect((root.parent/'completionist-map-gow2018-all-collectibles-production-research/.research-index/gow-caebcb027980.sqlite').as_uri()+'?mode=ro',uri=True)
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
md=Cs(CS_ARCH_X86,CS_MODE_64); md.detail=True
mode=sys.argv[1]
if mode=='schema':
 for row in con.execute("select name,sql from sqlite_master where type='table'"): print(row)
for arg in sys.argv[2:]:
 a=int(arg.split(':')[0],16)
 print('\nTARGET',hex(a))
 if mode=='dis':
  f=base.fn_for(con,a); end=int(arg.split(':')[1],16) if ':' in arg else f['end']; print('indexed',f)
  for i in md.disasm(pe.read(a,end-a),pe.image_base+a):
   notes=[]
   for op in i.operands:
    if op.type==3 and i.reg_name(op.mem.base)=='rip':
     t=i.address+i.size+op.mem.disp-pe.image_base
     s=con.execute('select text from strings where rva=?',(t,)).fetchone(); notes.append(hex(t)+((' '+repr(s[0])) if s else ''))
   print(f'{i.address-pe.image_base:08X} {i.bytes.hex():22} {i.mnemonic:7} {i.op_str} '+ ' | '.join(notes))
 if mode=='refs':
  for table,query in [('rip','select site,src_fn,mnemonic from rip_refs where target=?'),('edges','select site,src_fn,kind from edges where dest=?')]:
   print(table,[(hex(r[0]),hex(r[1]) if r[1] else None,r[2]) for r in con.execute(query,(a,))])
  needle=struct.pack('<Q',pe.image_base+a)
  for name,v,vs,rs,off in pe.sections:
   data=pe.data[off:off+rs]; p=0; found=[]
   while (p:=data.find(needle,p))>=0: found.append(hex(v+p)); p+=1
   if found: print('pointers',name,found)
 if mode=='qwords':
  for x in range(a,a+(int(arg.split(':')[1],16) if ':' in arg else 0x100),8):
   q=struct.unpack('<Q',pe.read(x,8))[0]; print(hex(x),hex(q),hex(q-pe.image_base) if q>=pe.image_base else '')
