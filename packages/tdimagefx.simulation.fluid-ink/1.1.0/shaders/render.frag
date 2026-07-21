// Display-only pass. Input 0 is encoded ink state; input 1 is source.
uniform float uMix;

layout(location = 0) out vec4 fragColor;

void main() {
    vec2 uv = vUV.st;
    vec3 ink = texture(sTD2DInputs[0], uv).rgb;
    vec4 src = texture(sTD2DInputs[1], uv);
    fragColor = TDOutputSwizzle(vec4(mix(src.rgb, ink, clamp(uMix, 0.0, 1.0)), src.a));
}
