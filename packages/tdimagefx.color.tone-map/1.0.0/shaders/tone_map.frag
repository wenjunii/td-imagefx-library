uniform float uMix;
uniform float uMode;
uniform float uExposure;
uniform float uWhitePoint;

layout(location = 0) out vec4 fragColor;

vec3 reinhardMap(vec3 color)
{
    float whiteSquared = max(uWhitePoint * uWhitePoint, 0.0001);
    return color * (1.0 + color / whiteSquared) / (1.0 + color);
}

vec3 acesFitted(vec3 color)
{
    return clamp((color * (2.51 * color + 0.03)) / (color * (2.43 * color + 0.59) + 0.14), 0.0, 1.0);
}

vec3 filmicMap(vec3 color)
{
    color = max(color - 0.004, 0.0);
    return (color * (6.2 * color + 0.5)) / (color * (6.2 * color + 1.7) + 0.06);
}

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    vec3 exposed = max(source.rgb * exp2(uExposure), vec3(0.0));
    float mode = floor(uMode + 0.5);
    vec3 mapped = mode < 0.5 ? reinhardMap(exposed) : (mode < 1.5 ? acesFitted(exposed) : filmicMap(exposed));
    fragColor = TDOutputSwizzle(vec4(mix(source.rgb, mapped, clamp(uMix, 0.0, 1.0)), source.a));
}
