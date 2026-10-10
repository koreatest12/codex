'use client';
export default function ErrorBoundary({reset}:{error:Error & {digest?:string},reset:()=>void}){return <main style={{padding:40,maxWidth:720,margin:'auto'}}><h1>화면 처리 중 오류가 발생했습니다.</h1><p>저장된 자료를 삭제하지 않고 화면을 다시 실행할 수 있습니다. 아직 저장하지 않은 편집 내용은 복구되지 않을 수 있습니다.</p><button className="primary" onClick={reset}>화면 다시 실행</button><p><a href="/">홈페이지 다시 열기</a></p></main>}
