layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform vec4 uShadowColor;
uniform vec4 uHighlightColor;
uniform float uContrast;

void main()
{
    vec4 source = texture(sTD2DInputs[0], vUV.st);
    float luma = dot(source.rgb, vec3(0.2126, 0.7152, 0.0722));
    luma = clamp((luma - 0.5) * max(uContrast, 0.0) + 0.5, 0.0, 1.0);
    vec3 mapped = mix(uShadowColor.rgb, uHighlightColor.rgb, luma);
    vec4 effect = vec4(mapped, source.a);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
