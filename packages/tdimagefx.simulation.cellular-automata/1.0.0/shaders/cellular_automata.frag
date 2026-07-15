uniform float uMix; uniform float uBirth; uniform float uSurvival; uniform float uSeed;
layout(location = 0) out vec4 fragColor;
void main() {
    vec2 uv = vUV.st; vec2 px = 1.0 / vec2(textureSize(sTD2DInputs[1], 0)); vec4 src = texture(sTD2DInputs[0], uv); float center = texture(sTD2DInputs[1], uv).r;
    float neighbors = 0.0;
    for (int y=-1; y<=1; ++y) for (int x=-1; x<=1; ++x) if (x != 0 || y != 0) neighbors += step(.5, texture(sTD2DInputs[1], uv + vec2(x,y)*px).r);
    float born = 1.0 - smoothstep(.55, 1.2, abs(neighbors - uBirth)); float lives = 1.0 - smoothstep(.55, 1.2, abs(neighbors - uSurvival));
    float cell = mix(born, lives, step(.5, center)); cell = max(cell, step(1.0-uSeed, dot(src.rgb, vec3(.3333))));
    vec3 color = mix(vec3(.015,.02,.04), vec3(.2,.9,1.0), cell);
    fragColor = TDOutputSwizzle(vec4(mix(src.rgb, color, clamp(uMix, 0.0, 1.0)), src.a));
}
