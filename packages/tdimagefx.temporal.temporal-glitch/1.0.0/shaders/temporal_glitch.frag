uniform float uMix; uniform float uAmount; uniform float uBlockSize; uniform float uPhase;

// Project-original cell hash. Integer-valued cells keep the result stable within a block.
float tdImageFxCellHash(vec2 p) {
    vec2 cell = mod(floor(p), vec2(251.0, 241.0));
    float mixed = cell.x * 73.0 + cell.y * 151.0 + cell.x * cell.y * 0.137;
    mixed = mod(mixed * mixed + mixed * 31.0 + 17.0, 65521.0);
    return fract(mixed / 65521.0 + mixed * 0.00000011920928955078125);
}
layout(location = 0) out vec4 fragColor;
void main() {
    vec2 uv = vUV.st; vec2 cell = floor(uv * max(2.0, uBlockSize)); float n = tdImageFxCellHash(cell + floor(uPhase * 127.0));
    vec2 shift = vec2((tdImageFxCellHash(cell.yx + floor(uPhase * 97.0)) - .5) * .12, 0.0); vec4 src = texture(sTD2DInputs[0], uv);
    vec3 old = texture(sTD2DInputs[1], uv + shift).rgb; vec3 effected = mix(src.rgb, old, step(1.0 - uAmount, n));
    fragColor = TDOutputSwizzle(vec4(mix(src.rgb, effected, clamp(uMix, 0.0, 1.0)), src.a));
}
