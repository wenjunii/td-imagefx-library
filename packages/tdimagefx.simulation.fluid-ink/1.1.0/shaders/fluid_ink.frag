// Private state: RGB = accumulated ink; A = marker identifying initialized state.
// Input 0 is source; input 1 is the previous private state.
uniform float uAdvection;
uniform float uDecay;
uniform float uInjection;
uniform float uPhase;

const float STATE_MARKER = 0.314159;

// Project-original cell hash. It avoids the commonly copied sine-hash expression.
float tdImageFxCellHash(vec2 p) {
    vec2 cell = mod(floor(p), vec2(251.0, 241.0));
    float mixed = cell.x * 73.0 + cell.y * 151.0 + cell.x * cell.y * 0.137;
    mixed = mod(mixed * mixed + mixed * 31.0 + 17.0, 65521.0);
    return fract(mixed / 65521.0 + mixed * 0.00000011920928955078125);
}
layout(location = 0) out vec4 fragColor;

void main() {
    vec2 uv = vUV.st;
    vec4 src = texture(sTD2DInputs[0], uv);
    vec2 cell = floor(uv * 48.0);
    float phase = floor(uPhase * 83.0);
    float a = tdImageFxCellHash(cell + phase);
    float b = tdImageFxCellHash(cell.yx - phase);
    vec2 flow = normalize(vec2(a - 0.5, b - 0.5) + vec2(0.0001));
    vec4 prior = texture(sTD2DInputs[1], uv - flow * uAdvection);
    float initialized = 1.0 - step(0.02, abs(prior.a - STATE_MARKER));
    vec3 advected = prior.rgb * initialized * clamp(uDecay, 0.0, 1.0);
    float luma = dot(src.rgb, vec3(0.2126, 0.7152, 0.0722));
    float ink = luma * clamp(uInjection, 0.0, 2.0);
    vec3 nextInk = max(advected, src.rgb * ink);
    fragColor = TDOutputSwizzle(vec4(nextInk, STATE_MARKER));
}
