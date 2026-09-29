#!/usr/bin/env node
/** Rebuild a presentation from a retained template, profile and declarative content. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import {spawnSync} from 'node:child_process';

const flags=Object.fromEntries(process.argv.slice(2).reduce((a,x,i,all)=>{if(x.startsWith('--'))a.push([x.slice(2),all[i+1]]);return a;},[]));
const required=['spec','profile','runtime','output','build-dir'];
function check(ok,msg){if(!ok)throw new Error(msg);}
for(const key of required)check(flags[key]&&!flags[key].startsWith('--'),`Required: --${key}`);
const files=Object.fromEntries(required.map(k=>[k,path.resolve(flags[k])]));
const readJson=async f=>JSON.parse(await fs.readFile(f,'utf8'));
const [spec,profile,runtime]=await Promise.all([readJson(files.spec),readJson(files.profile),readJson(files.runtime)]);
check(spec.schemaVersion===1&&profile.schemaVersion===1,'Unsupported content/profile schemaVersion');
check(Array.isArray(spec.slides)&&spec.slides.length>0,'No content slides');
check(!await fs.stat(files.output).catch(()=>null),'Output exists; choose a new output path');
check(![files.spec,files.profile,files.runtime].includes(files.output),'Output must not replace an input');
const template=path.resolve(path.dirname(files.profile),profile.template);
check(template!==files.output,'Output must not replace the template');
await fs.access(template);
check(spec.slides.reduce((a,s)=>a+s.seconds,0)===spec.durationSeconds,'Speaking times do not match durationSeconds');
for(const s of spec.slides){
 check(profile.roles[s.role],`Unknown template role: ${s.role}`);
 check(typeof s.title==='string'&&s.title.trim(),'Slide title required');
 check(Array.isArray(s.cues)&&s.cues.length>0&&Array.isArray(s.sources),'Cues and sources required');
 for(const b of s.blocks??[]){
  check(['text','table','figure'].includes(b.type),`Unsupported block: ${b.type}`);
  check(Array.isArray(b.frame)&&b.frame.length===4&&b.frame.every(Number.isFinite),'Block frame must be [left,top,width,height]');
  const [x,y,w,h]=b.frame;check(w>0&&h>0&&x>=0&&y>=0&&x+w<=profile.slideSize[0]+.1&&y+h<=profile.slideSize[1]+.1,'Block outside slide');
  if(s.role!=='cover'&&profile.contentBottom)check(y+h<=profile.contentBottom+.1,'Content overlaps reserved template footer');
  if(b.type==='figure')await fs.access(path.resolve(path.dirname(files.spec),b.path));
  if(b.type==='text')check(profile.textStyles[b.style],`Unknown text style: ${b.style}`);
  if(b.type==='table'){
   check(Array.isArray(b.values)&&b.values.length>0&&b.values.every(r=>r.length===b.values[0].length),'Ragged or empty table');
   check(b.columnWidths?.length===b.values[0].length,'Table widths must cover every column');
  }
 }
}
const moduleRoot=path.resolve(path.dirname(files.runtime),runtime.nodeModules);
const req=createRequire(path.join(moduleRoot,'__xenium_loader.cjs'));
const toolPackage=await readJson(path.join(moduleRoot,'@oai/artifact-tool/package.json'));
if(runtime.artifactToolVersion)check(toolPackage.version===runtime.artifactToolVersion,'Artifact Tool version differs from runtime configuration');
const {PresentationFile,FileBlob}=await import(pathToFileURL(req.resolve('@oai/artifact-tool')).href);
const {GlobalFonts}=await import(pathToFileURL(req.resolve('@napi-rs/canvas')).href);
for(const fontFile of runtime.fontFiles??[]){
 const f=path.resolve(path.dirname(files.runtime),fontFile);await fs.access(f);GlobalFonts.registerFromPath(f);
}
const fontFamilies=new Set(GlobalFonts.families.map(f=>f.family));
for(const family of profile.requiredFonts??[])check(fontFamilies.has(family),`Required template font unavailable: ${family}`);
const templateBytes=await fs.readFile(template);
const p=await PresentationFile.importPptx(await FileBlob.load(template));
const originals=[...p.slides.items];
check(p.slides.items[0].frame.width===profile.slideSize[0]&&p.slides.items[0].frame.height===profile.slideSize[1],'Template dimensions differ from profile');
await fs.mkdir(files['build-dir'],{recursive:true});
const artifactDir=files['build-dir'];
const position=([left,top,width,height])=>({left,top,width,height});
const shapeText=s=>String(s.text??'');
function select(slide,selector){
 const found=slide.shapes.items.filter(s=>s.name===selector.name&&(selector.text===undefined||shapeText(s)===selector.text));
 check(found.length===1,`Template shape missing or ambiguous: ${JSON.stringify(selector)}`);return found[0];
}
function style(shape,style){shape.text.style={...style,autoFit:'none'};}
const manifest={template,spec:files.spec,profile:files.profile,figures:[],tableSlides:[],slideRoles:[]};
for(let i=0;i<spec.slides.length;i++){
 const data=spec.slides[i],role=profile.roles[data.role];
 check(Number.isInteger(role.sourceSlide)&&originals[role.sourceSlide-1],'Template sourceSlide unavailable');
 const slide=originals[role.sourceSlide-1].duplicate();slide.moveTo(p.slides.items.length-1);
 // Resolve all selectors before edits so a field value cannot affect later matching.
 const fields=Object.entries(role.fields??{}).map(([key,cfg])=>({key,cfg,shape:select(slide,cfg.selector)}));
 const remove=(role.remove??[]).map(selector=>select(slide,selector));
 for(const {key,cfg,shape} of fields){
  const value=key==='title'?data.title:data.fields?.[key];
  check(typeof value==='string',`Missing field ${key} for ${data.role}`);
  shape.text=value;if(cfg.frame)shape.position=position(cfg.frame);if(cfg.style)style(shape,cfg.style);
 }
 for(const s of remove)s.delete();
 for(let j=0;j<(data.blocks??[]).length;j++){
  const b=data.blocks[j],frame=position(b.frame),name=`content-${i+1}-${j+1}`;
  if(b.type==='text'){
   const s=slide.shapes.add({name,geometry:'textbox',position:frame,fill:'none',line:{fill:'none',width:0}});
   s.text=b.text;style(s,profile.textStyles[b.style]);
  }else if(b.type==='table'){
   const t=slide.tables.add({name,rows:b.values.length,columns:b.values[0].length,...frame,values:b.values,columnWidths:b.columnWidths});
   const ts=profile.tableStyle;
   t.styleOptions={headerRow:false,bandedRows:false};t.borders.assign({style:'solid',fill:ts.borderColor,width:ts.borderWidth});
   for(let r=0;r<b.values.length;r++)for(let c=0;c<b.values[0].length;c++){
    const cell=t.getCell(r,c);cell.fill=r===0?ts.headerFill:(r%2?ts.bodyFills[0]:ts.bodyFills[1]);
    cell.text.style={typeface:ts.typeface,fontSize:b.fontSize??ts.fontSize,bold:r===0||(b.totalRow&&r===b.values.length-1),color:r===0?ts.headerText:ts.bodyText};
    t.cells.block({row:r,column:c,rowCount:1,columnCount:1}).assign({borders:Object.fromEntries(['top','bottom','left','right'].map(side=>[side,{width:ts.borderWidth,color:ts.borderColor}]))});
   }
   manifest.tableSlides.push(i+1);
  }else{
   const source=path.resolve(path.dirname(files.spec),b.path),bytes=await fs.readFile(source);
   check(bytes.subarray(0,8).equals(Buffer.from('89504e470d0a1a0a','hex')),'Current fixed-figure branch requires a finalized PNG');
   const pixelSize=[bytes.readUInt32BE(16),bytes.readUInt32BE(20)],ratio=pixelSize[0]/pixelSize[1];
   const width=Math.min(frame.width,frame.height*ratio),height=width/ratio;
   const fitted={left:frame.left+(frame.width-width)/2,top:frame.top+(frame.height-height)/2,width,height};
   const image=slide.images.add({name,blob:bytes,contentType:'image/png',alt:b.alt??'',fit:'contain',position:fitted});image.lockAspectRatio=true;
   manifest.figures.push({slide:i+1,source,pixelSize,frame:fitted});
  }
 }
 slide.speakerNotes.textFrame.setText(data.cues.map(c=>'- '+c).join('\n')+'\n\nSources (reference only):\n'+data.sources.join('\n'));
 manifest.slideRoles.push({slide:i+1,role:data.role,sourceSlide:role.sourceSlide});
}
for(const s of originals)s.delete();
check(p.slides.items.length===spec.slides.length,'Unexpected generated slide count');
const candidate=path.join(artifactDir,'candidate.pptx');
await (await PresentationFile.exportPptx(p)).save(candidate);
await fs.writeFile(path.join(artifactDir,'manifest.json'),JSON.stringify(manifest,null,2));
for(const [key,value] of [['content',spec],['template-profile',profile],['runtime',runtime]])await fs.writeFile(path.join(artifactDir,`${key}.json`),JSON.stringify(value,null,2));
const python=path.resolve(path.dirname(files.runtime),runtime.python);
const run=(args)=>{const r=spawnSync(python,args,{encoding:'utf8'});check(r.status===0,`${args[0]} failed:\n${r.stdout}\n${r.stderr}`);return JSON.parse(r.stdout);};
const ownDir=path.dirname(fileURLToPath(import.meta.url));
const contentReceipt=run([path.join(ownDir,'verify_template_presentation.py'),'--candidate',candidate,'--spec',files.spec,'--profile',files.profile,'--manifest',path.join(artifactDir,'manifest.json'),'--report',path.join(artifactDir,'content-verification.json')]);
const toolDir=path.resolve(path.dirname(files.runtime),runtime.presentationTools);
const packageReceipt=run([path.join(toolDir,'inspect_presentation_package_integrity.py'),candidate,'--fail-on-findings']);
const layoutReceipt=run([path.join(toolDir,'inspect_presentation_layout_geometry.py'),candidate,'--expected-slide-count',String(spec.slides.length),'--expected-slide-size-emu',profile.slideSize.map(v=>Math.round(v*9525)).join(','),...manifest.tableSlides.flatMap(n=>['--require-native-table-slide',String(n)]),'--validate-heading-fit','--fail-on-findings']);
const imported=await PresentationFile.importPptx(await FileBlob.load(candidate));
check(imported.slides.items.length===spec.slides.length,'Export/import changed slide count');
for(let i=0;i<spec.slides.length;i++){
 const img=await imported.export({slide:imported.slides.items[i],format:'png',scale:1.5});
 await fs.writeFile(path.join(artifactDir,`slide-${i+1}.png`),new Uint8Array(await img.arrayBuffer()));
}
check((await fs.readFile(template)).equals(templateBytes),'Source template changed during build');
await fs.mkdir(path.dirname(files.output),{recursive:true});
await fs.copyFile(candidate,files.output,fs.constants.COPYFILE_EXCL);
const notesPath=path.join(artifactDir,'speaker-cues.md');
await fs.writeFile(notesPath,spec.slides.map((s,i)=>`## ${i+1}. ${s.title}\n\n${s.cues.map(c=>'- '+c).join('\n')}`).join('\n\n')+'\n');
const receipt={output:files.output,template,templateUnchanged:true,slideCount:spec.slides.length,durationSeconds:spec.durationSeconds,contentReceipt,packageReceipt,layoutReceipt,checksumsPerformed:false,rendered:true,powerPointTested:false,node:process.version,artifactToolVersion:toolPackage.version};
await fs.writeFile(path.join(artifactDir,'verification.json'),JSON.stringify(receipt,null,2));
console.log(JSON.stringify({output:files.output,receipt:path.join(artifactDir,'verification.json'),slides:spec.slides.length,checks:'pass'}));
