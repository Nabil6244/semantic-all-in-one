// A lit Earth whose ice spreads from the poles: ice covers every latitude above iceLat(t) (degrees).
import * as THREE from '/agent_kit/lib/three.module.js';

export async function makeGlobe(canvas, { radius = 0.62, camZ = 3.4, x = 0, y = 0, texture = '/whatif-engine/assets/textures/earth_bluemarble_5400.jpg' } = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(1);
  renderer.setSize(canvas.width, canvas.height, false);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(30, canvas.width / canvas.height, 0.1, 100);
  camera.position.set(0, 0, camZ);
  const tex = await new THREE.TextureLoader().loadAsync(texture);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  const uni = { map: { value: tex }, iceLat: { value: 90 }, sunDir: { value: new THREE.Vector3(-0.8, 0.25, 0.55).normalize() } };
  const mat = new THREE.ShaderMaterial({
    uniforms: uni,
    vertexShader: `varying vec2 vUv; varying vec3 vN; varying vec3 vP;
      void main(){ vUv=uv; vN=normalize(mat3(modelMatrix)*normal); vP=(modelMatrix*vec4(position,1.)).xyz;
      gl_Position=projectionMatrix*viewMatrix*vec4(vP,1.); }`,
    fragmentShader: `uniform sampler2D map; uniform float iceLat; uniform vec3 sunDir; varying vec2 vUv; varying vec3 vN; varying vec3 vP;
      float h(vec2 p){ return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453); }
      float n(vec2 p){ vec2 i=floor(p), f=fract(p); f=f*f*(3.-2.*f);
        return mix(mix(h(i),h(i+vec2(1,0)),f.x),mix(h(i+vec2(0,1)),h(i+vec2(1,1)),f.x),f.y); }
      void main(){
        vec3 c = texture2D(map, vUv).rgb;
        c = mix(c, vec3(dot(c,vec3(.3,.5,.2)))*vec3(.75,.95,1.0), .35);           // cooler, calmer colours
        float lat = (vUv.y-.5)*180.;
        float edge = iceLat + (n(vUv*vec2(60.,30.))-.5)*3. + (n(vUv*vec2(160.,80.))-.5)*1.2;                       // ragged ice edge
        float ice = smoothstep(edge-0.4, edge+0.4, abs(lat));
        vec3 icec = vec3(.88,.95,.98) * (.92 + .08*n(vUv*vec2(90.,45.)));
        c = mix(c, icec, ice);
        float d = max(dot(normalize(vN), sunDir), 0.);
        float light = .08 + 1.05*pow(d,.8);
        vec3 col = c*light;
        float rim = pow(1.-max(dot(normalize(vN), normalize(cameraPosition-vP)),0.), 3.);
        col += vec3(.35,.75,.85)*rim*.35;
        gl_FragColor = vec4(col,1.);
        #include <colorspace_fragment>
      }`,
  });
  const earth = new THREE.Mesh(new THREE.SphereGeometry(radius, 128, 96), mat);
  earth.rotation.z = 0.41;                                                         // axial tilt
  earth.position.set(x, y, 0);
  scene.add(earth);
  // atmosphere halo
  const halo = new THREE.Mesh(new THREE.SphereGeometry(radius * 1.035, 64, 48), new THREE.ShaderMaterial({
    side: THREE.BackSide, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    vertexShader: `varying vec3 vN; varying vec3 vP; void main(){ vN=normalize(mat3(modelMatrix)*normal); vP=(modelMatrix*vec4(position,1.)).xyz; gl_Position=projectionMatrix*viewMatrix*vec4(vP,1.);} `,
    fragmentShader: `varying vec3 vN; varying vec3 vP; void main(){ float k=pow(max(0., .62-dot(normalize(vN), normalize(vP-cameraPosition)*-1.)), 3.);
      gl_FragColor=vec4(vec3(.35,.8,.9)*k*1.1, k*.8); }`,
  }));
  halo.position.copy(earth.position);
  scene.add(halo);
  return {
    render({ iceLat = 90, spin = 0, scale = 1, camX = 0 } = {}) {
      uni.iceLat.value = iceLat;
      earth.rotation.y = spin;
      earth.scale.setScalar(scale); halo.scale.setScalar(scale);
      camera.position.x = camX;
      renderer.render(scene, camera);
    },
  };
}
