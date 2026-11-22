import {spawn} from 'node:child_process';
import path from 'node:path';
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FRAMES = path.join(HERE, 'out', 'frames');
const OUT = path.join(HERE, 'out');

const FPS = 30;
const count = fs.readdirSync(FRAMES).filter((f) => f.endsWith('.png')).length;
if (!count) {
  console.error('no frames to encode');
  process.exit(1);
}

const run = (args) =>
  new Promise((resolve, reject) => {
    const p = spawn('ffmpeg', args, {stdio: ['ignore', 'ignore', 'pipe']});
    let err = '';
    p.stderr.on('data', (d) => (err += d.toString()));
    p.on('close', (code) =>
      code === 0 ? resolve() : reject(new Error(`ffmpeg exited ${code}\n${err.slice(-2000)}`)),
    );
  });

// H.264 / yuv420p so the file plays everywhere, including GitHub and
// browsers that refuse odd dimensions.
const common = [
  '-y',
  '-framerate', String(FPS),
  '-i', path.join(FRAMES, 'f%04d.png'),
  '-c:v', 'libx264',
  '-preset', 'slow',
  '-crf', '18',
  '-pix_fmt', 'yuv420p',
  '-profile:v', 'high',
  '-level', '4.1',
  '-movflags', '+faststart',
];

const mp4 = path.join(OUT, 'previewgen-promo.mp4');
await run([...common, mp4]);
console.log('mp4  ', mp4, (fs.statSync(mp4).size / 1024 / 1024).toFixed(2), 'MB');

// A silent, looping WebP for the README hero and for the GitHub social
// preview. GitHub renders animated WebP inline, so this is what the README
// actually plays. It has to stay light enough to commit, so the hero runs
// at 960x540 and 20 fps: the motion is slow enough that the frame rate
// drop is invisible, and the file lands near 4 MB instead of 28 MB.
const webp = path.join(OUT, 'previewgen-promo.webp');
await run([
  '-y',
  '-framerate', String(FPS),
  '-i', path.join(FRAMES, 'f%04d.png'),
  '-vf', 'scale=960:540,fps=20',
  '-c:v', 'libwebp',
  '-lossless', '0',
  '-q:v', '52',
  '-compression_level', '6',
  '-loop', '0',
  webp,
]);
console.log('webp ', webp, (fs.statSync(webp).size / 1024 / 1024).toFixed(2), 'MB');

// A small poster frame for the README <img> fallback.
const poster = path.join(OUT, 'previewgen-promo-poster.jpg');
await run([
  '-y',
  '-i', path.join(FRAMES, 'f0030.png'),
  '-vf', 'scale=1280:-1',
  '-q:v', '5',
  poster,
]);
console.log('poster', poster, (fs.statSync(poster).size / 1024).toFixed(0), 'KB');
