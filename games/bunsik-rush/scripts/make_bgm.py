import numpy as np, wave
from pathlib import Path
sr=22050; bpm=120; beat=60/bpm; length=32; out=np.zeros(sr*length)
rng=np.random.default_rng(42)
def add(start,dur,midi,vol,kind='lead'):
 n=int(dur*sr); t=np.arange(n)/sr; f=440*2**((midi-69)/12)
 if kind=='lead': y=np.sin(2*np.pi*f*t)+.22*np.sin(4*np.pi*f*t)+.08*np.sin(6*np.pi*f*t)
 else: y=np.sin(2*np.pi*f*t)+.15*np.sin(4*np.pi*f*t)
 env=np.minimum(t/.012,1)*np.maximum(1-t/dur,0)**1.8
 i=int(start*sr); end=min(i+n,len(out)); out[i:end]+=y[:end-i]*env[:end-i]*vol
chords=[(48,[60,64,67]),(55,[59,62,67]),(45,[60,64,69]),(53,[60,65,69])]
melodies=[[72,76,79,76,74,72,67,72],[71,74,79,74,76,74,71,67],[72,76,81,79,76,72,74,76],[77,76,72,69,72,74,76,79], [79,81,79,76,74,76,72,67],[74,76,79,83,79,76,74,71],[76,79,81,84,81,79,76,72],[77,76,74,72,69,67,71,72]]
for bar in range(16):
 base=bar*2; root,triad=chords[bar%4]
 for b in range(4):
  add(base+b*beat,.35,root+(12 if b%2 else 0),.13,'bass')
  for m in triad:add(base+b*beat+.25,.17,m,.045)
 for j,m in enumerate(melodies[bar%8]):add(base+j*.25,.2,m,.15)
 for j in range(8):
  t=np.arange(int(.055*sr))/sr;y=rng.normal(0,1,len(t));y=np.r_[0,np.diff(y)]*np.exp(-t*80)*.023;i=int((base+j*.25)*sr);out[i:i+len(t)]+=y
 for b in range(4):
  t=np.arange(int(.17*sr))/sr
  y=(np.sin(2*np.pi*(65*t-80*t*t))*np.exp(-t*26)*.19 if b%2==0 else rng.normal(0,1,len(t))*np.exp(-t*36)*.045)
  i=int((base+b*.5)*sr);out[i:i+len(t)]+=y
out=np.tanh(out)*.82
fade=int(.012*sr);out[:fade]*=np.linspace(0,1,fade);out[-fade:]*=np.linspace(1,0,fade)
p=Path('bunsik-rush-bgm.wav')
with wave.open(str(p),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(sr);w.writeframes((out*32767).astype('<i2').tobytes())
assert np.isfinite(out).all() and np.max(np.abs(out))<1
print(f'Original BGM: {length}s, {bpm} BPM, peak {np.max(np.abs(out)):.3f}')
