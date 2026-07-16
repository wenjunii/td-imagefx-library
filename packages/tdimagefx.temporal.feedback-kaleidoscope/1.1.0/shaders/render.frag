// Display-only pass. Input 0 is private wet state; input 1 is the current source.
uniform float uMix;

layout(location = 0) out vec4 fragColor;

void main() {
    vec2 uv = vUV.st;
    vec4 wet = texture(sTD2DInputs[0], uv);
    vec4 src = texture(sTD2DInputs[1], uv);
    vec3 color = mix(src.rgb, wet.rgb, clamp(uMix, 0.0, 1.0));
    fragColor = TDOutputSwizzle(vec4(color, src.a));
}
