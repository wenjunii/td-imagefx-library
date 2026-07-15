layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uTemperature;
uniform float uTint;
uniform float uStrength;

const vec3 LUMA = vec3(0.2126, 0.7152, 0.0722);

void main()
{
    vec4 source = texture(sTD2DInputs[0], vUV.st);
    float luminance = dot(source.rgb, LUMA);
    vec3 temperatureAxis = vec3(0.30, 0.04, -0.30) * uTemperature;
    vec3 tintAxis = vec3(0.12, -0.24, 0.12) * uTint;
    vec3 balanced = source.rgb * (vec3(1.0) + (temperatureAxis + tintAxis) * uStrength);
    balanced += vec3(luminance - dot(balanced, LUMA));
    vec4 effect = vec4(max(balanced, vec3(0.0)), source.a);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
