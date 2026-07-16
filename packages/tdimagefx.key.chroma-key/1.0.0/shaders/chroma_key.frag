uniform float uMix;
uniform vec4 uKeyColor;
uniform float uSimilarity;
uniform float uSoftness;
uniform float uClipBlack;
uniform float uClipWhite;

layout(location = 0) out vec4 fragColor;

vec2 chroma(vec3 rgb)
{
    return vec2(
        -0.114572 * rgb.r - 0.385428 * rgb.g + 0.5 * rgb.b,
         0.5 * rgb.r - 0.454153 * rgb.g - 0.045847 * rgb.b
    );
}

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    float distanceFromKey = distance(chroma(source.rgb), chroma(uKeyColor.rgb));
    float matte = smoothstep(uSimilarity, uSimilarity + max(uSoftness, 0.000001), distanceFromKey);
    float low = min(uClipBlack, uClipWhite);
    float high = max(uClipBlack, uClipWhite);
    matte = smoothstep(low, max(high, low + 0.000001), matte);
    vec4 keyed = vec4(source.rgb, source.a * matte);
    fragColor = TDOutputSwizzle(mix(source, keyed, clamp(uMix, 0.0, 1.0)));
}
