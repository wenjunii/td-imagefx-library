// Display-only pass. Input 0 is encoded Gray-Scott state; input 1 is source.
uniform float uMix;

layout(location = 0) out vec4 fragColor;

void main() {
    vec2 uv = vUV.st;
    vec2 chemicals = texture(sTD2DInputs[0], uv).rg;
    vec4 src = texture(sTD2DInputs[1], uv);
    float a = chemicals.r;
    float b = chemicals.g;
    vec3 color = vec3(clamp(a - b, 0.0, 1.0), b, 1.0 - a);
    fragColor = TDOutputSwizzle(vec4(mix(src.rgb, color, clamp(uMix, 0.0, 1.0)), src.a));
}
