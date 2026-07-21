// Stateful pass. Input 0 is source; input 1 is the previous wet state.
uniform float uAmount;
uniform float uBlockSize;
uniform float uPhase;

// Project-original cell hash. Integer-valued cells keep the result stable within a block.
float tdImageFxCellHash(vec2 p) {
    vec2 cell = mod(floor(p), vec2(251.0, 241.0));
    float mixed = cell.x * 73.0 + cell.y * 151.0 + cell.x * cell.y * 0.137;
    mixed = mod(mixed * mixed + mixed * 31.0 + 17.0, 65521.0);
    return fract(mixed / 65521.0 + mixed * 0.00000011920928955078125);
}
layout(location = 0) out vec4 fragColor;

void main() {
    vec2 uv = vUV.st;
    vec2 cell = floor(uv * max(2.0, uBlockSize));
    float frame = floor(uPhase * 127.0);
    float selection = tdImageFxCellHash(cell + frame);
    vec2 shift = vec2((tdImageFxCellHash(cell.yx + floor(uPhase * 97.0)) - 0.5) * 0.12, 0.0);
    vec4 src = texture(sTD2DInputs[0], uv);
    vec3 prior = texture(sTD2DInputs[1], uv + shift).rgb;
    vec3 wet = mix(src.rgb, prior, step(1.0 - clamp(uAmount, 0.0, 1.0), selection));
    fragColor = TDOutputSwizzle(vec4(wet, src.a));
}
