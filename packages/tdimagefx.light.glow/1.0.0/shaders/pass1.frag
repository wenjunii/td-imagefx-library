layout(location = 0) out vec4 fragColor;

uniform float uThreshold;
uniform vec4 uGlowColor;

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    float luminance = dot(source.rgb, vec3(0.2126, 0.7152, 0.0722));
    float mask = smoothstep(max(uThreshold, 0.0), max(uThreshold, 0.0) + 0.2, luminance);
    vec3 energy = source.rgb * mix(vec3(1.0), uGlowColor.rgb, 0.75) * mask;
    fragColor = TDOutputSwizzle(vec4(energy, source.a));
}
