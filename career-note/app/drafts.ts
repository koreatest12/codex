export function makeDrafts(text:string,name:string,hash:string,file:{id:string,name:string}){
const clean=text.replace(/\r/g,'').replace(/[ \t]+/g,' ').trim();
if(clean.length<80)throw new Error('문서에서 충분한 텍스트를 추출하지 못했습니다. 이미지·스캔 PDF는 OCR 처리 후 올려주세요.');
if(clean.length>150000)throw new Error('문서가 너무 깁니다. 15만 자 이하로 나눠 주세요.');
const source=name;const common={source,files:[file],review:'파일 텍스트에서 규칙으로 생성한 초안입니다. 날짜·학위·성과 수치와 문장 연결을 원본과 대조하세요.',tags:'업로드 자동 생성,검토 전'};
const sections=clean.split(/\n(?=(?:경력\s*\d|경험 기술서\s*\d|자기소개서\s*\d|■|프로젝트|PROJECT))/i);
const relevant=sections.filter(s=>/경험 기술서|프로젝트|시뮬레이터|MCP|장애|개발|구현|성과/.test(s));
const projectText=(relevant.length?relevant:sections).join('\n\n').slice(0,65000);
const highlights=clean.split('\n').map(x=>x.trim()).filter(x=>x.length>12&&/경력|담당|운영|개발|구현|성과|전공|학점|취득|재학/.test(x)).slice(0,12).join('\n');
return [
{id:'upload-'+hash,type:'application',title:name,description:clean,summary:highlights||clean.slice(0,700),subtitle:'업로드 원본 · 텍스트 추출 완료',...common},
{id:'resume-'+hash,type:'resume',title:name.replace(/\.[^.]+$/,'')+' · 이력서 초안',subtitle:'원문 기반 자동 생성 · 검토 전',description:'[원문에서 추출한 핵심 항목]\n'+(highlights||'본문을 확인하세요.')+'\n\n[지원서 추출 본문]\n'+clean,...common},
{id:'portfolio-'+hash,type:'project',title:name.replace(/\.[^.]+$/,'')+' · 포트폴리오 초안',subtitle:'경험·프로젝트 관련 본문 자동 분류',description:projectText,...common}
];}
