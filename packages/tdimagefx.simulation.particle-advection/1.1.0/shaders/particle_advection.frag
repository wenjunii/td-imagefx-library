// Private state: RGB = advected particle trails; A = initialized-state marker.
// Input 0 is source; input 1 is the previous private state.
uniform float uSpeed;
uniform float uDecay;
uniform float uThreshold;
uniform float uPhase;

const float STATE_MARKER = 0.618034;

layout(location = 0) out vec4 fragColor;

void main() {
    vec2 uv = vUV.st;
    vec4 src = texture(sTD2DInputs[0], uv);
    float angle = sin(uv.x * 19.0 + uPhase) * 3.0 + cos(uv.y * 17.0 - uPhase) * 2.0;
    vec2 flow = vec2(cos(angle), sin(angle)) * uSpeed;
    vec4 prior = texture(sTD2DInputs[1], uv - flow);
    float initialized = 1.0 - step(0.02, abs(prior.a - STATE_MARKER));
    vec3 advected = prior.rgb * initialized * clamp(uDecay, 0.0, 1.0);
    float peak = max(src.r, max(src.g, src.b));
    float seed = smoothstep(clamp(uThreshold, 0.0, 1.0), 1.0, peak);
    vec3 nextParticles = max(advected, src.rgb * seed);
    fragColor = TDOutputSwizzle(vec4(nextParticles, STATE_MARKER));
}
